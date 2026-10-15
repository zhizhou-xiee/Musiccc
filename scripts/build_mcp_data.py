#!/usr/bin/env python3
"""Build the read-only MCP song payload from reviewed project sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SONG_DIR = ROOT / "data" / "songs" / "jieyue"
TIMELINE_PATH = SONG_DIR / "timeline.reference.json"
METADATA_PATH = SONG_DIR / "metadata.json"
DETAIL_PATH = SONG_DIR / "source" / "detailed-listening-annotations.json"
CURVE_PATH = SONG_DIR / "experiments" / "mss-curve-poc" / "outputs" / "mss.curves.json"
OUTPUT_PATH = SONG_DIR / "mcp.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def uniform_points(
    sample_times: list[int], values: list[int | None], start_ms: int, end_ms: int, target: int = 5
) -> list[dict[str, int]]:
    candidates = [
        (time_ms, value)
        for time_ms, value in zip(sample_times, values)
        if start_ms <= time_ms <= end_ms and value is not None
    ]
    if not candidates:
        return []
    if len(candidates) <= target:
        chosen = candidates
    else:
        indexes = [round(index * (len(candidates) - 1) / (target - 1)) for index in range(target)]
        chosen = [candidates[index] for index in indexes]
    return [{"time_ms": time_ms, "value": value} for time_ms, value in chosen]


def main() -> None:
    metadata = read_json(METADATA_PATH)
    timeline = read_json(TIMELINE_PATH)
    detail = read_json(DETAIL_PATH)
    curve_data = read_json(CURVE_PATH)
    performer_names = {item["id"]: item["display_name"] for item in timeline["performers"]}
    line_by_id = {item["id"]: item for item in timeline["lines"]}
    sample_times = curve_data["sampling"]["sample_times_ms"]
    segments: list[dict[str, Any]] = []

    for section in timeline["sections"]:
        if section["id"] == "mv_credits":
            continue
        lyrics = []
        for line_id in section["line_ids"]:
            line = line_by_id[line_id]
            lyrics.append(
                {
                    "id": line["id"],
                    "text": line["text"],
                    "start_ms": line["start_ms"],
                    "end_ms": line["end_ms"],
                    "performers": [
                        {
                            "id": performer["id"],
                            "name": performer_names[performer["id"]],
                            "role": performer["role"],
                        }
                        for performer in line["performers"]
                    ],
                    "timing_status": {
                        "start": line["timing"]["start"]["status"],
                        "end": line["timing"]["vocal_end"]["status"],
                    },
                }
            )

        observations = [
            {
                "id": event["id"],
                "start_ms": event["start_ms"],
                **({"end_ms": event["end_ms"]} if event.get("end_ms") is not None else {}),
                "description": event["description_zh"],
                "certainty": event["certainty"],
                "source": "human_listening_annotation",
            }
            for event in detail["events"]
            if event["section_id"] == section["id"]
        ]

        curves = [
            {
                "id": curve["id"],
                "label": curve["label_zh"],
                "status": "automatic_unverified",
                "scale": "whole_song_percentile_02_98_quantized_0_63",
                "points": uniform_points(
                    sample_times,
                    curve["quantized"],
                    section["start_ms"],
                    min(section["end_ms"], metadata["duration_ms"]),
                ),
            }
            for curve in curve_data["curves"]
        ]
        segments.append(
            {
                "index": len(segments),
                "id": section["id"],
                "title": section["title"],
                "start_ms": section["start_ms"],
                "end_ms": min(section["end_ms"], metadata["duration_ms"]),
                "lyrics": lyrics,
                "music_observations": observations,
                "acoustic_curves": curves,
            }
        )

    output = {
        "schema_version": "1.0.0",
        "revision": "jieyue-timeline-0.2.2-perception-1.0.0",
        "perception_route": "pre_generated_objective_music_summary_plus_numeric_curves",
        "perception_notice": "返回内容来自人工听音标注与离线自动测量，不代表接收模型直接听见了原始音频。",
        "song": {
            "id": metadata["song_id"],
            "title": metadata["title"],
            "version": metadata["version"],
            "duration_ms": metadata["duration_ms"],
            "credits": metadata["credits"],
            "performers": timeline["performers"],
            "media": {
                "video_url": metadata["media"]["video"]["deployment_url"],
                "audio_url": metadata["media"]["audio"]["deployment_url"],
            },
        },
        "unknown": ["melody_contour", "key", "meter"],
        "segments": segments,
        "limits": {
            "segment_count": len(segments),
            "max_segments_per_response": 1,
            "native_audio_content": False,
        },
        "provenance": {
            "lyrics_and_performers": "human_timeline_annotation",
            "music_observations": "human_listening_annotation",
            "acoustic_curves": "automatic_ffmpeg_measurement_unverified",
        },
    }
    write_json(OUTPUT_PATH, output)
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "segments": len(segments),
                "lyrics": sum(len(segment["lyrics"]) for segment in segments),
                "observations": sum(len(segment["music_observations"]) for segment in segments),
                "bytes": OUTPUT_PATH.stat().st_size,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
