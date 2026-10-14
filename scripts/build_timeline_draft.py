#!/usr/bin/env python3
"""Build an explicitly unverified lyric timeline from Whisper token timestamps.

The script never replaces the supplied lyric text with ASR output. Whisper is
used only as a source of candidate timestamps; known lyrics are aligned to the
recognized token stream by pinyin and must be reviewed by a human.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypinyin import Style, lazy_pinyin


HAN_RE = re.compile(r"[\u3400-\u9fff]")
SECTION_RE = re.compile(r"^[\[［](.+?)[\]］]$")
PERFORMER_RE = re.compile(r"^【(.+?)】(.+)$")


@dataclass
class Syllable:
    value: str
    char: str
    line_index: int | None
    start_ms: int | None = None
    end_ms: int | None = None
    probability: float | None = None


def pinyin_for_char(char: str) -> str:
    return lazy_pinyin(char, style=Style.NORMAL, errors="ignore")[0].lower()


def normalized_syllables(text: str, line_index: int | None) -> list[Syllable]:
    return [
        Syllable(pinyin_for_char(char), char, line_index)
        for char in HAN_RE.findall(text)
    ]


def normalize_section(raw: str, seen: dict[str, int]) -> tuple[str, str]:
    key = re.sub(r"[\s_-]+", "", raw).lower()
    mapping = {
        "清唱无伴奏": ("a_cappella", "清唱无伴奏"),
        "verse1": ("verse_1", "Verse 1"),
        "verse2": ("verse_2", "Verse 2"),
        "prechorus": ("pre_chorus_1", "Pre-Chorus"),
        "prechorus2": ("pre_chorus_2", "Pre-Chorus 2"),
        "bridge": ("bridge", "Bridge"),
        "finalchorus": ("final_chorus", "Final Chorus"),
    }
    if key == "chorus":
        seen[key] = seen.get(key, 0) + 1
        return f"chorus_{seen[key]}", f"Chorus {seen[key]}"
    return mapping.get(key, (key or "unknown", raw.strip()))


def parse_roles(spec: str, names: str) -> list[dict[str, str]]:
    ids = [int(value) for value in re.findall(r"\d+", spec)]
    display_names = [name.strip().replace("vv…家的", "vv家的") for name in names.split("、")]
    if len(ids) != len(display_names):
        raise ValueError(f"performer count mismatch: {spec!r} / {names!r}")

    roles = ["lead"] * len(ids)
    if "主唱" in spec:
        roles[0] = "lead"
        tail = spec.split("主唱", 1)[1]
        if "backing" in tail.lower():
            roles[1:] = ["backing"] * (len(ids) - 1)
        elif "合唱" in tail:
            roles[1:] = ["chorus"] * (len(ids) - 1)
    elif len(ids) > 1:
        roles = ["ensemble"] * len(ids)

    return [
        {
            "id": f"performer-{performer_id:02d}",
            "display_name": display_name,
            "role": role,
        }
        for performer_id, display_name, role in zip(ids, display_names, roles, strict=True)
    ]


def parse_lyrics(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lines: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    section_counts: dict[str, int] = {}
    current_section: dict[str, Any] | None = None
    current_performers: list[dict[str, str]] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith("#") or re.match(
            r"^(作曲|作词|混音|演唱)[/：:]", raw_line
        ):
            continue

        section_match = SECTION_RE.match(raw_line)
        if section_match:
            section_id, title = normalize_section(section_match.group(1), section_counts)
            current_section = {
                "id": section_id,
                "title": title,
                "line_ids": [],
            }
            sections.append(current_section)
            continue

        performer_match = PERFORMER_RE.match(raw_line)
        if performer_match:
            current_performers = parse_roles(
                performer_match.group(1), performer_match.group(2)
            )
            continue

        if current_section is None or not current_performers:
            raise ValueError(f"lyric line has no section or performer: {raw_line!r}")

        line_id = f"line-{len(lines) + 1:03d}"
        line = {
            "id": line_id,
            "section_id": current_section["id"],
            "text": raw_line,
            "performers": [performer.copy() for performer in current_performers],
        }
        lines.append(line)
        current_section["line_ids"].append(line_id)

    return lines, sections


def whisper_syllables(path: Path) -> list[Syllable]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: list[Syllable] = []
    for segment in payload["transcription"]:
        for token in segment.get("tokens", []):
            text = token.get("text", "")
            chars = HAN_RE.findall(text)
            if not chars:
                continue
            start_ms = int(token["offsets"]["from"])
            end_ms = int(token["offsets"]["to"])
            duration = max(1, end_ms - start_ms)
            for char_index, char in enumerate(chars):
                char_start = start_ms + round(duration * char_index / len(chars))
                char_end = start_ms + round(duration * (char_index + 1) / len(chars))
                result.append(
                    Syllable(
                        pinyin_for_char(char),
                        char,
                        None,
                        char_start,
                        char_end,
                        float(token.get("p", 0.0)),
                    )
                )
    return result


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def similarity(left: str, right: str) -> tuple[float, str]:
    if left == right:
        return 3.0, "exact"
    if left and right and left[0] == right[0] and edit_distance(left, right) <= 2:
        return 0.8, "near"
    if edit_distance(left, right) == 1:
        return 0.4, "near"
    return -3.0, "mismatch"


def align(
    expected: list[Syllable], recognized: list[Syllable]
) -> list[tuple[int, int, str]]:
    rows = len(expected) + 1
    columns = len(recognized) + 1
    scores = [[0.0] * columns for _ in range(rows)]
    trace = [[""] * columns for _ in range(rows)]

    for row in range(1, rows):
        scores[row][0] = scores[row - 1][0] - 1.0
        trace[row][0] = "up"
    for column in range(1, columns):
        scores[0][column] = scores[0][column - 1] - 0.65
        trace[0][column] = "left"

    for row in range(1, rows):
        for column in range(1, columns):
            match_score, _ = similarity(
                expected[row - 1].value, recognized[column - 1].value
            )
            choices = (
                (scores[row - 1][column - 1] + match_score, "diag"),
                (scores[row - 1][column] - 1.0, "up"),
                (scores[row][column - 1] - 0.65, "left"),
            )
            scores[row][column], trace[row][column] = max(choices, key=lambda item: item[0])

    row = len(expected)
    column = len(recognized)
    matches: list[tuple[int, int, str]] = []
    while row or column:
        direction = trace[row][column]
        if direction == "diag":
            _, match_type = similarity(
                expected[row - 1].value, recognized[column - 1].value
            )
            if match_type != "mismatch":
                matches.append((row - 1, column - 1, match_type))
            row -= 1
            column -= 1
        elif direction == "up":
            row -= 1
        else:
            column -= 1

    matches.reverse()
    return matches


def interpolate_missing(lines: list[dict[str, Any]], duration_ms: int) -> None:
    known_indices = [
        index for index, line in enumerate(lines) if line.get("start_ms") is not None
    ]
    if not known_indices:
        raise ValueError("alignment produced no timed lines")

    for index, line in enumerate(lines):
        if line.get("start_ms") is not None:
            continue
        previous = max((item for item in known_indices if item < index), default=None)
        following = min((item for item in known_indices if item > index), default=None)
        if previous is None:
            right = lines[following]["start_ms"]
            left = 0
            count = following + 1
            position = index + 1
        elif following is None:
            left = lines[previous]["end_ms"]
            right = duration_ms
            count = len(lines) - previous
            position = index - previous
        else:
            left = lines[previous]["end_ms"]
            right = lines[following]["start_ms"]
            count = following - previous
            position = index - previous
        span = max(count, right - left)
        line["start_ms"] = round(left + span * (position - 1) / count)
        line["end_ms"] = round(left + span * position / count)
        line["alignment"]["method"] = "interpolated"
        line["alignment"]["confidence"] = 0.0


def finalize_boundaries(lines: list[dict[str, Any]], duration_ms: int) -> None:
    for index, line in enumerate(lines):
        next_start = lines[index + 1]["start_ms"] if index + 1 < len(lines) else duration_ms
        line["start_ms"] = max(0, min(duration_ms, int(line["start_ms"])))
        line["end_ms"] = max(line["start_ms"] + 1, int(line["end_ms"]))
        if line["end_ms"] > next_start:
            line["end_ms"] = max(line["start_ms"] + 1, next_start)
        line["end_ms"] = min(duration_ms, line["end_ms"])


def format_time(milliseconds: int) -> str:
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def render_review(payload: dict[str, Any]) -> str:
    names = {
        performer["id"]: performer["display_name"]
        for performer in payload["performers"]
    }
    rows = [
        "# 《借月》歌词时间轴人工校对表",
        "",
        "> 自动生成初稿，不得视为准确时间戳。请以最终 MP3 母带逐句试听校对。",
        "",
        "| ID | 候选时间 | 演唱者 | 置信度 | 复核标记 | 歌词 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for line in payload["lines"]:
        performers = "、".join(
            f"{names[item['id']]}（{item['role']}）" for item in line["performers"]
        )
        flags = "、".join(line["alignment"].get("review_flags", [])) or "—"
        rows.append(
            "| {id} | {start}–{end} | {performers} | {confidence:.3f} | {flags} | {text} |".format(
                id=line["id"],
                start=format_time(line["start_ms"]),
                end=format_time(line["end_ms"]),
                performers=performers,
                confidence=line["alignment"]["confidence"],
                flags=flags,
                text=line["text"].replace("|", "\\|"),
            )
        )
    rows.extend(
        [
            "",
            "## 标记说明",
            "",
            "- `low_asr_probability`：歌唱识别 token 概率较低。",
            "- `low_coverage`：已知歌词中与识别结果匹配的音节比例较低。",
            "- `long_span_per_syllable`：候选区间相对歌词长度异常偏长，可能包含拖音或间奏。",
            "- `short_line_ambiguous`：歌词过短，重复词或拖音容易造成错位。",
            "- `prompt_conditioned`：该段使用已知歌词提示做了局部重跑，时间更集中但仍须人工试听。",
            "",
        ]
    )
    return "\n".join(rows)


def render_lrc(payload: dict[str, Any]) -> str:
    rows = ["[ti:借月]", "[offset:0]"]
    for line in payload["lines"]:
        minutes, remainder = divmod(line["start_ms"], 60_000)
        seconds = remainder / 1_000
        rows.append(f"[{minutes:02d}:{seconds:05.2f}]{line['text']}")
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lyrics", type=Path, required=True)
    parser.add_argument("--whisper-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path)
    parser.add_argument("--lrc-output", type=Path)
    parser.add_argument(
        "--section-whisper",
        action="append",
        default=[],
        metavar="SECTION_ID=JSON",
        help="Replace one section's global ASR matches with a prompted local Whisper run.",
    )
    parser.add_argument("--duration-ms", type=int, required=True)
    parser.add_argument("--audio-sha256", required=True)
    args = parser.parse_args()

    lines, sections = parse_lyrics(args.lyrics)
    expected: list[Syllable] = []
    for line_index, line in enumerate(lines):
        expected.extend(normalized_syllables(line["text"], line_index))
    recognized = whisper_syllables(args.whisper_json)
    matches = align(expected, recognized)

    by_line: dict[int, list[tuple[Syllable, str]]] = {}
    line_method: dict[int, str] = {}
    for expected_index, recognized_index, match_type in matches:
        line_index = expected[expected_index].line_index
        if line_index is None:
            continue
        by_line.setdefault(line_index, []).append((recognized[recognized_index], match_type))

    for override in args.section_whisper:
        section_id, separator, json_path = override.partition("=")
        if not separator:
            raise ValueError(f"invalid --section-whisper value: {override!r}")
        section_line_indices = [
            index for index, line in enumerate(lines) if line["section_id"] == section_id
        ]
        if not section_line_indices:
            raise ValueError(f"unknown section id for override: {section_id!r}")
        override_expected: list[Syllable] = []
        for line_index in section_line_indices:
            override_expected.extend(normalized_syllables(lines[line_index]["text"], line_index))
        override_recognized = whisper_syllables(Path(json_path))
        override_matches = align(override_expected, override_recognized)
        for line_index in section_line_indices:
            by_line.pop(line_index, None)
            line_method[line_index] = "prompted_section_whisper_pinyin_alignment"
        for expected_index, recognized_index, match_type in override_matches:
            line_index = override_expected[expected_index].line_index
            if line_index is not None:
                by_line.setdefault(line_index, []).append(
                    (override_recognized[recognized_index], match_type)
                )

    for line_index, line in enumerate(lines):
        aligned = by_line.get(line_index, [])
        exact = sum(match_type == "exact" for _, match_type in aligned)
        near = sum(match_type == "near" for _, match_type in aligned)
        expected_count = len(normalized_syllables(line["text"], line_index))
        coverage = (exact + 0.5 * near) / max(1, expected_count)
        asr_probability = (
            sum(item.probability or 0.0 for item, _ in aligned) / len(aligned)
            if aligned
            else 0.0
        )
        confidence = coverage * (0.35 + 0.65 * asr_probability)
        review_flags: list[str] = []
        if line_index in line_method:
            review_flags.append("prompt_conditioned")
        if asr_probability < 0.4:
            review_flags.append("low_asr_probability")
        if coverage < 0.6:
            review_flags.append("low_coverage")
        if expected_count <= 4:
            review_flags.append("short_line_ambiguous")
        line["alignment"] = {
            "status": "draft_unverified",
            "method": line_method.get(line_index, "whisper_token_pinyin_alignment"),
            "confidence": round(confidence, 3),
            "coverage": round(coverage, 3),
            "asr_probability": round(asr_probability, 3),
            "matched_syllables": len(aligned),
            "expected_syllables": expected_count,
            "review_flags": review_flags,
        }
        if aligned:
            line["start_ms"] = min(item.start_ms for item, _ in aligned)
            line["end_ms"] = max(item.end_ms for item, _ in aligned)
        else:
            line["start_ms"] = None
            line["end_ms"] = None

    interpolate_missing(lines, args.duration_ms)
    finalize_boundaries(lines, args.duration_ms)
    for line in lines:
        expected_count = line["alignment"]["expected_syllables"]
        span_per_syllable = (line["end_ms"] - line["start_ms"]) / max(1, expected_count)
        if span_per_syllable > 1_800:
            line["alignment"]["review_flags"].append("long_span_per_syllable")

    line_by_id = {line["id"]: line for line in lines}
    for section in sections:
        section_lines = [line_by_id[line_id] for line_id in section["line_ids"]]
        section["start_ms"] = min(line["start_ms"] for line in section_lines)
        section["end_ms"] = max(line["end_ms"] for line in section_lines)

    performers: dict[str, str] = {}
    for line in lines:
        for performer in line["performers"]:
            performers[performer["id"]] = performer["display_name"]
            performer.pop("display_name")

    payload = {
        "schema_version": "0.1.0",
        "song_id": "jieyue",
        "title": "借月",
        "timeline_timebase": {
            "asset": "借月MMM.mp3",
            "duration_ms": args.duration_ms,
            "sha256": args.audio_sha256,
        },
        "alignment": {
            "status": "draft_unverified",
            "manual_review_required": True,
            "asr_engine": "whisper.cpp 1.9.4",
            "asr_model": "ggml-small multilingual",
            "method": "pinyin_global_sequence_alignment",
            "section_overrides": [
                value.partition("=")[0] for value in args.section_whisper
            ],
            "recognized_syllables": len(recognized),
            "expected_syllables": len(expected),
        },
        "performers": [
            {"id": performer_id, "display_name": performers[performer_id]}
            for performer_id in sorted(performers)
        ],
        "sections": sections,
        "lines": lines,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.review_output:
        args.review_output.parent.mkdir(parents=True, exist_ok=True)
        args.review_output.write_text(render_review(payload), encoding="utf-8")
    if args.lrc_output:
        args.lrc_output.parent.mkdir(parents=True, exist_ok=True)
        args.lrc_output.write_text(render_lrc(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
