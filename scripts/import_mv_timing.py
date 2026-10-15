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
    parser.add_argument("--review-export", type=Path)
    parser.add_argument("--timing-corrections", type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_if_needed(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)


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
                    "subtitle_start": {
                        "value_ms": subtitle["start_ms"],
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
            "original_name": "借月_分拍资料.json",
            "sha256": sha256(args.timing_json),
        },
        "subtitle_srt": {
            "original_name": "借月_歌词字幕.srt",
            "sha256": sha256(args.subtitle_srt),
        },
        "reference_md": {
            "original_name": "借月_分拍资料.md",
            "sha256": sha256(args.reference_md),
        },
    }

    output = {
        "schema_version": "0.2.2",
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

    if args.review_export:
        review_export = json.loads(args.review_export.read_text(encoding="utf-8"))
        if review_export["song_id"] != output["song_id"]:
            raise ValueError("Review export belongs to a different song")
        if review_export["timeline_timebase"]["sha256"] != output["timeline_timebase"]["sha256"]:
            raise ValueError("Review export uses a different master")
        if len(review_export["lines"]) != len(output["lines"]):
            raise ValueError("Review export line count differs")

        verified = 0
        flagged = 0
        for base_line, reviewed_line in zip(output["lines"], review_export["lines"], strict=True):
            if base_line["id"] != reviewed_line["id"] or base_line["text"] != reviewed_line["text"]:
                raise ValueError("Review export line identity differs")
            review = reviewed_line.get("manual_review", {})
            status = review.get("status", "pending")
            if status == "pending":
                continue
            if review.get("candidate_start_ms") != base_line["start_ms"]:
                raise ValueError(f"{base_line['id']}: review start candidate differs")
            if review.get("candidate_end_ms") != base_line["end_ms"]:
                raise ValueError(f"{base_line['id']}: review end candidate differs")

            base_line["manual_review"] = review
            if status == "verified":
                verified += 1
                base_line["start_ms"] = reviewed_line["start_ms"]
                base_line["end_ms"] = reviewed_line["end_ms"]
                base_line["timing"]["start"] = {
                    "value_ms": reviewed_line["start_ms"],
                    "source": "manual_listening_review",
                    "status": "verified",
                }
                base_line["timing"]["vocal_end"] = {
                    "value_ms": reviewed_line["end_ms"],
                    "source": "manual_listening_review",
                    "status": "verified",
                }
                base_line["timing"]["start_frame"] = {
                    "value": round(reviewed_line["start_ms"] * raw["meta"]["video_fps"] / 1000),
                    "fps": raw["meta"]["video_fps"],
                    "source": "derived_from_verified_start",
                }
                if base_line["timing"].get("exception"):
                    base_line["timing"]["exception"]["resolution"] = "manually_verified"
            elif status == "flagged":
                flagged += 1

        pending = len(output["lines"]) - verified - flagged
        output["manual_review"] = {
            "status": "complete" if verified == len(output["lines"]) else "in_progress",
            "summary": {
                "verified_lines": verified,
                "flagged_lines": flagged,
                "pending_lines": pending,
                "total_lines": len(output["lines"]),
            },
            "source": {
                "original_name": "timeline.reviewed (2).json",
                "stored_as": "manual-review-line-005.json",
                "sha256": sha256(args.review_export),
                "exported_at": review_export.get("alignment", {}).get("review_summary", {}).get("exported_at"),
            },
        }
        output["provenance"]["source_files"]["manual_review_export"] = output["manual_review"]["source"]
        if any(line["id"] == "line-005" and line.get("manual_review", {}).get("status") == "verified" for line in output["lines"]):
            output["provenance"]["line_005_exception"] += " 之后已通过母带试听人工确认。"
            output["alignment"]["review_scope"] = [
                item for item in output["alignment"]["review_scope"] if "第 5 句" not in item
            ]

    if args.timing_corrections:
        corrections = json.loads(args.timing_corrections.read_text(encoding="utf-8"))
        if corrections["song_id"] != output["song_id"]:
            raise ValueError("Timing corrections belong to a different song")
        line_by_id = {line["id"]: line for line in output["lines"]}
        for correction in corrections["corrections"]:
            line = line_by_id[correction["line_id"]]
            field = correction["field"]
            value_ms = int(correction["value_ms"])
            timing_value = {
                "value_ms": value_ms,
                "source": correction["source"],
                "status": correction["status"],
                "note": correction["note"],
            }
            if field == "start":
                line["start_ms"] = value_ms
                line["timing"]["start"] = timing_value
                line["timing"]["start_frame"] = {
                    "value": round(value_ms * raw["meta"]["video_fps"] / 1000),
                    "fps": raw["meta"]["video_fps"],
                    "source": "derived_from_verified_start",
                }
            elif field == "vocal_end":
                line["end_ms"] = value_ms
                line["timing"]["vocal_end"] = timing_value
            else:
                raise ValueError(f"Unsupported timing correction field: {field}")

        correction_source = {
            "stored_as": args.timing_corrections.name,
            "sha256": sha256(args.timing_corrections),
            "recorded_at": corrections.get("recorded_at"),
            "count": len(corrections["corrections"]),
        }
        output["provenance"]["source_files"]["manual_timing_corrections"] = correction_source
        output.setdefault("manual_review", {})["targeted_timing_corrections"] = correction_source

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    args.source_dir.mkdir(parents=True, exist_ok=True)
    copy_if_needed(args.timing_json, args.source_dir / "mv-timing-reference.json")
    copy_if_needed(args.reference_md, args.source_dir / "mv-timing-reference.md")
    copy_if_needed(args.subtitle_srt, args.source_dir / "lyrics-subtitle-reference.srt")
    if args.review_export:
        copy_if_needed(args.review_export, args.source_dir / "manual-review-line-005.json")
    if args.timing_corrections:
        copy_if_needed(args.timing_corrections, args.source_dir / args.timing_corrections.name)
    args.subtitle_output.parent.mkdir(parents=True, exist_ok=True)
    copy_if_needed(args.subtitle_srt, args.subtitle_output)

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
