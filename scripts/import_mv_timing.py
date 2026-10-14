#!/usr/bin/env python3
"""Import the editor's final-MV timing references into the canonical review timeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


SECTION_IDS = {
    "清唱（无伴奏）": "a_cappella",
    "前奏": "intro",
    "Verse 1": "verse_1",
    "Pre-Chorus": "pre_chorus_1",
    "Chorus": "chorus_1",
    "间奏": "interlude",
    "Verse 2": "verse_2",
    "Pre-Chorus 2": "pre_chorus_2",
    "Chorus 2": "chorus_2",
    "Bridge": "bridge",
    "Final Chorus": "final_chorus",
    "尾奏": "outro",
    "片尾字幕（仅 MV）": "mv_credits",
}

LINE_SECTION_IDS = {
    "清唱": "a_cappella",
    "Verse 1": "verse_1",
    "Pre-Chorus": "pre_chorus_1",
    "Chorus": "chorus_1",
    "Verse 2": "verse_2",
    "Pre-Chorus 2": "pre_chorus_2",
    "Chorus 2": "chorus_2",
    "Bridge": "bridge",
    "Final Chorus": "final_chorus",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timing-json", type=Path, required=True)
    parser.add_argument("--subtitle-srt", type=Path, required=True)
    parser.add_argument("--reference-md", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--subtitle-output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ms(seconds: float) -> int:
    return round(float(seconds) * 1000)


def normalize_lyric(text: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]", "", text, flags=re.UNICODE)


def srt_ms(value: str) -> int:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (((int(hours) * 60 + int(minutes)) * 60) + int(seconds)) * 1000 + int(millis)


def parse_srt(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8-sig").strip()
    entries = []
    pattern = re.compile(
        r"(?ms)^(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3}) --> "
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.+?)(?=\n\n|\Z)"
    )
    for match in pattern.finditer(content):
        label, separator, lyric = match.group(4).partition("：")
        if not separator:
            raise ValueError(f"SRT entry {match.group(1)} has no full-width colon")
        entries.append(
            {
                "no": int(match.group(1)),
                "start_ms": srt_ms(match.group(2)),
                "end_ms": srt_ms(match.group(3)),
                "display_credit": label,
                "text": lyric,
            }
        )
    return entries


def coarse_time_ms(value: str, audio_duration_ms: int) -> int:
    if value == "结尾":
        return audio_duration_ms
    minutes, seconds = value.split(":")
    return (int(minutes) * 60 + int(seconds)) * 1000


def main() -> None:
    args = parse_args()
    raw = json.loads(args.timing_json.read_text(encoding="utf-8"))
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    subtitles = parse_srt(args.subtitle_srt)

    if len(raw["lines"]) != 72 or len(draft["lines"]) != 72 or len(subtitles) != 72:
        raise ValueError("Expected exactly 72 lines in JSON, draft, and SRT")

    performer_by_number = {
        int(person["id"].removeprefix("performer-")): person for person in draft["performers"]
    }
    subtitle_by_number = {entry["no"]: entry for entry in subtitles}
    draft_by_number = {index + 1: line for index, line in enumerate(draft["lines"])}

    lines = []
    for raw_line in raw["lines"]:
        number = raw_line["no"]
        candidate = draft_by_number[number]
        subtitle = subtitle_by_number[number]
        if normalize_lyric(raw_line["text"]) != normalize_lyric(candidate["text"]):
            raise ValueError(f"Line {number}: timing JSON and draft lyric differ")
        if normalize_lyric(raw_line["text"]) != normalize_lyric(subtitle["text"]):
            raise ValueError(f"Line {number}: timing JSON and SRT lyric differ")
        if ms(raw_line["start"]) != subtitle["start_ms"]:
            raise ValueError(f"Line {number}: timing JSON and SRT starts differ")

        performers = []
        for performer_number, display_name in zip(raw_line["lead_ids"], raw_line["lead"], strict=True):
            person = performer_by_number[performer_number]
            if person["display_name"] != display_name:
                raise ValueError(f"Line {number}: lead performer ID/name mismatch")
            performers.append({"id": person["id"], "role": "lead"})
        for performer_number, display_name in zip(raw_line["backing_ids"], raw_line["backing"], strict=True):
            person = performer_by_number[performer_number]
            if person["display_name"] != display_name:
                raise ValueError(f"Line {number}: backing performer ID/name mismatch")
            performers.append({"id": person["id"], "role": "backing"})

        exception = None
        if number == 5:
            exception = {
                "kind": "reconstructed_onset",
                "note": "原始打拍漏按；00:40.000 是参照第二段主歌对应位置补出的时间。",
            }

        lines.append(
            {
                "id": candidate["id"],
                "section_id": LINE_SECTION_IDS[raw_line["section"]],
                "text": candidate["text"],
                "performers": performers,
                "start_ms": ms(raw_line["start"]),
                "end_ms": ms(raw_line["vocal_end"]),
                "timing": {
                    "start": {
                        "value_ms": ms(raw_line["start"]),
                        "source": "human_waveform_mark",
                        "status": "reference",
                    },
                    "vocal_end": {
                        "value_ms": ms(raw_line["vocal_end"]),
                        "source": "separated_vocal_estimate",
                        "status": "estimate",
                    },
                    "subtitle_end": {
                        "value_ms": subtitle["end_ms"],
                        "source": "editorial_subtitle_timing",
                        "status": "display_only",
                    },
                    "start_frame": {
                        "value": raw_line["start_frame_30fps"],
                        "fps": 30,
                    },
                    "exception": exception,
                },
                "alignment": candidate["alignment"],
            }
        )

    lines_by_section: dict[str, list[str]] = {}
    for line in lines:
        lines_by_section.setdefault(line["section_id"], []).append(line["id"])

    sections = []
    for raw_section in raw["sections"]:
        section_id = SECTION_IDS[raw_section["name"]]
        sections.append(
            {
                "id": section_id,
                "title": raw_section["name"],
                "start_ms": ms(raw_section["start"]),
                "end_ms": ms(raw_section["end"]),
                "line_ids": lines_by_section.get(section_id, []),
                "media": ["video"] if section_id == "mv_credits" else ["audio", "video"],
                "note": raw_section["note"],
                "source": "mv_editor_reference",
            }
        )

    audio_duration_ms = draft["timeline_timebase"]["duration_ms"]
    instruments = []
    for index, event in enumerate(raw["instruments_by_zhouzhou"], start=1):
        instruments.append(
            {
                "id": f"instrument-event-{index:02d}",
                "start_ms": coarse_time_ms(event["start"], audio_duration_ms),
                "end_ms": coarse_time_ms(event["end"], audio_duration_ms),
                "instruments": [item.strip() for item in event["instruments"].split("+")],
                "source": "human_annotation",
                "precision": "coarse",
            }
        )

    source_files = {
        "timing_json": {
            "original_name": args.timing_json.name,
            "sha256": sha256(args.timing_json),
        },
        "subtitle_srt": {
            "original_name": args.subtitle_srt.name,
            "sha256": sha256(args.subtitle_srt),
        },
        "reference_md": {
            "original_name": args.reference_md.name,
            "sha256": sha256(args.reference_md),
        },
    }

    output = {
        "schema_version": "0.2.0",
        "song_id": draft["song_id"],
        "title": draft["title"],
        "timeline_timebase": draft["timeline_timebase"],
        "video_reference": {
            "fps": raw["meta"]["video_fps"],
            "production_resolution": raw["meta"]["video_size"],
            "duration_ms": ms(raw["meta"]["mv_duration_sec"]),
            "audio_offset_ms": ms(raw["meta"]["offset_mv_vs_master_sec"]),
            "note": "这是终版制作参考规格；当前收到并获准公开的预览资产为 1280×720。",
        },
        "provenance": {
            "primary_start_source": "舟舟于 2026-10-14 观察人声波形后逐句标记。",
            "vocal_end_source": "由分离人声估算；伴奏密集的副歌可靠性较低。",
            "line_005_exception": "漏按的第 5 句开口参照第二段主歌对应位置补为 00:40.000。",
            "source_files": source_files,
        },
        "alignment": {
            **draft["alignment"],
            "status": "human_onsets_reference",
            "manual_review_required": True,
            "review_scope": [
                "确认第 5 句补出的开口时间。",
                "复核估算的唱完时间，尤其是伴奏密集的副歌。",
                "不得把自动节拍当作已验证的工程速度网格。",
            ],
        },
        "tempo": {
            "bpm": raw["meta"]["tempo_bpm_estimate"],
            "beat_period_ms": ms(raw["meta"]["beat_period_sec"]),
            "source": "automatic_librosa_detection",
            "status": "unverified_reference_only",
        },
        "performers": draft["performers"],
        "sections": sections,
        "lines": lines,
        "instrument_events": instruments,
        "mv_scenes": [
            {
                "id": scene["key"],
                "start_ms": ms(scene["start"]),
                "end_ms": ms(scene["end"]),
                "description": scene["desc"],
                "source": "mv_editor_reference",
            }
            for scene in raw["mv_scenes"]
        ],
        "beats": {
            "timestamps_ms": [ms(value) for value in raw["beats_auto"]],
            "source": "automatic_librosa_detection",
            "status": "unverified_reference_only",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    args.source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.timing_json, args.source_dir / "mv-timing-reference.json")
    shutil.copyfile(args.reference_md, args.source_dir / "mv-timing-reference.md")
    args.subtitle_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.subtitle_srt, args.subtitle_output)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "lines": len(lines),
                "sections": len(sections),
                "beats": len(output["beats"]["timestamps_ms"]),
                "scenes": len(output["mv_scenes"]),
                "instrument_events": len(instruments),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
