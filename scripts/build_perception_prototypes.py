#!/usr/bin/env python3
"""Build local A/B music-perception prototypes from the final master.

The experiment deliberately keeps the lyric/timeline payload identical across
all variants. Candidate A adds compact measured acoustic features. Candidate B
adds deterministic prose assembled from existing human annotations and a small
number of measured loudness relations. No waveform samples are persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SONG_DIR = ROOT / "data" / "songs" / "jieyue"
DEFAULT_OUTPUT = SONG_DIR / "experiments" / "perception"

LOUDNESS_PATTERN = re.compile(
    r"Integrated loudness:\s+I:\s+(-?\d+(?:\.\d+)?) LUFS"
    r".*?Loudness range:\s+LRA:\s+(\d+(?:\.\d+)?) LU"
    r".*?True peak:\s+Peak:\s+(-?\d+(?:\.\d+)?) dBFS",
    re.DOTALL,
)
SPECTRAL_PATTERN = re.compile(
    r"lavfi\.aspectralstats\.\d+\."
    r"(centroid|flatness|flux|rolloff)=([^\s]+)"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_ffmpeg(audio: Path, start_ms: int, end_ms: int, audio_filter: str) -> str:
    duration_seconds = max((end_ms - start_ms) / 1000, 0.05)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{start_ms / 1000:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(audio),
        "-af",
        audio_filter,
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stderr


def measure_loudness(audio: Path, start_ms: int, end_ms: int) -> dict[str, float]:
    output = run_ffmpeg(
        audio,
        start_ms,
        end_ms,
        "ebur128=peak=true:framelog=verbose",
    )
    matches = LOUDNESS_PATTERN.findall(output)
    if not matches:
        raise RuntimeError(f"Unable to parse loudness for {start_ms}-{end_ms} ms")
    integrated, loudness_range, true_peak = matches[-1]
    return {
        "integrated_lufs": float(integrated),
        "loudness_range_lu": float(loudness_range),
        "true_peak_dbfs": float(true_peak),
    }


def measure_loudness_profile(
    audio: Path, start_ms: int, end_ms: int
) -> list[float]:
    duration = end_ms - start_ms
    boundaries = [
        start_ms,
        start_ms + round(duration / 3),
        start_ms + round(duration * 2 / 3),
        end_ms,
    ]
    return [
        measure_loudness(audio, boundaries[index], boundaries[index + 1])[
            "integrated_lufs"
        ]
        for index in range(3)
    ]


def measure_spectral(audio: Path, start_ms: int, end_ms: int) -> dict[str, float]:
    output = run_ffmpeg(
        audio,
        start_ms,
        end_ms,
        (
            "aresample=11025,"
            "aspectralstats=win_size=2048:"
            "measure=centroid+flatness+rolloff+flux,"
            "ametadata=print"
        ),
    )
    values: dict[str, list[float]] = {
        "centroid": [],
        "flatness": [],
        "flux": [],
        "rolloff": [],
    }
    for key, raw_value in SPECTRAL_PATTERN.findall(output):
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if math.isfinite(value):
            values[key].append(value)

    if not all(values.values()):
        raise RuntimeError(f"Unable to parse spectral data for {start_ms}-{end_ms} ms")

    return {
        "spectral_centroid_hz_median": round(statistics.median(values["centroid"])),
        "spectral_rolloff_hz_median": round(statistics.median(values["rolloff"])),
        "spectral_flatness_median": round(statistics.median(values["flatness"]), 4),
        "spectral_flux_median": round(statistics.median(values["flux"]), 4),
    }


def unique_in_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def line_payload(
    line: dict[str, Any], performer_names: dict[str, str]
) -> dict[str, Any]:
    return {
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
    }


def overlapping_instruments(
    section: dict[str, Any], events: list[dict[str, Any]]
) -> list[str]:
    result: list[str] = []
    for event in events:
        overlap = min(section["end_ms"], event["end_ms"]) - max(
            section["start_ms"], event["start_ms"]
        )
        minimum_overlap = max(
            1_000,
            round((section["end_ms"] - section["start_ms"]) * 0.10),
        )
        if overlap >= minimum_overlap:
            result.extend(instrument for instrument in event["instruments"] if instrument)
    return unique_in_order(result)


def describe_performers(lines: list[dict[str, Any]]) -> str:
    lead_names = unique_in_order(
        [
            performer["name"]
            for line in lines
            for performer in line["performers"]
            if performer["role"] == "lead"
        ]
    )
    backing_names = unique_in_order(
        [
            performer["name"]
            for line in lines
            for performer in line["performers"]
            if performer["role"] != "lead"
        ]
    )
    if not lines:
        return "本段没有歌词，是纯器乐段落"
    if lead_names:
        text = f"主唱依次为{'、'.join(lead_names)}"
    else:
        text = "现有资料未标出独立主唱"
    if backing_names:
        text += f"；和声包含{'、'.join(backing_names)}"
    return text


def describe_dynamics(profile: list[float], previous_lufs: float | None) -> str:
    change = profile[-1] - profile[0]
    if change >= 1.5:
        contour = "自动测量显示后段整体比前段更响"
    elif change <= -1.5:
        contour = "自动测量显示后段整体比前段更轻"
    else:
        contour = "自动测量显示前三分之一与后三分之一的整体响度接近"

    current = statistics.mean(profile)
    if previous_lufs is None:
        return contour
    relative = current - previous_lufs
    if relative >= 1.5:
        return f"{contour}，并且整体高于上一段"
    if relative <= -1.5:
        return f"{contour}，并且整体低于上一段"
    return f"{contour}，与上一段的整体响度接近"


def make_common_segment(
    section: dict[str, Any],
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "song_id": "jieyue",
        "segment_id": section["id"],
        "title": section["title"],
        "start_ms": section["start_ms"],
        "end_ms": section["end_ms"],
        "lyrics": lines,
    }


def token_proxy(payload: dict[str, Any]) -> dict[str, int]:
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    byte_count = len(compact.encode("utf-8"))
    return {
        "utf8_bytes": byte_count,
        "unicode_characters": len(compact),
        "estimated_tokens_low": math.ceil(byte_count / 4),
        "estimated_tokens_high": math.ceil(byte_count / 3),
    }


def cumulative_cost(segments: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "utf8_bytes": 0,
        "unicode_characters": 0,
        "estimated_tokens_low": 0,
        "estimated_tokens_high": 0,
    }
    for segment in segments:
        measured = token_proxy(segment)
        for key in totals:
            totals[key] += measured[key]
    return totals


def write_json(path: Path, payload: dict[str, Any]) -> int:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")
    if not args.audio.is_file():
        raise SystemExit(f"Audio file not found: {args.audio}")

    started = time.perf_counter()
    metadata = read_json(SONG_DIR / "metadata.json")
    timeline = read_json(SONG_DIR / "timeline.reference.json")
    audio_sha256 = sha256_file(args.audio)
    expected_sha256 = metadata["media"]["audio"]["sha256"]
    if audio_sha256 != expected_sha256:
        raise SystemExit(
            "Audio SHA-256 does not match the registered final master: "
            f"expected {expected_sha256}, got {audio_sha256}"
        )
    performer_names = {
        performer["id"]: performer["display_name"]
        for performer in timeline["performers"]
    }
    audio_end = metadata["duration_ms"]
    sections = [
        section
        for section in timeline["sections"]
        if "audio" in section["media"] and section["start_ms"] < audio_end
    ]

    measurements: dict[str, dict[str, Any]] = {}
    loudness_measurement_seconds = 0.0
    spectral_measurement_seconds = 0.0
    for section in sections:
        start_ms = section["start_ms"]
        end_ms = min(section["end_ms"], audio_end)
        measurement_started = time.perf_counter()
        loudness = measure_loudness(args.audio, start_ms, end_ms)
        loudness_profile = measure_loudness_profile(args.audio, start_ms, end_ms)
        loudness_measurement_seconds += time.perf_counter() - measurement_started
        measurement_started = time.perf_counter()
        spectral = measure_spectral(args.audio, start_ms, end_ms)
        spectral_measurement_seconds += time.perf_counter() - measurement_started
        beats = [
            value
            for value in timeline["beats"]["timestamps_ms"]
            if start_ms <= value < end_ms
        ]
        section_lines = [
            line for line in timeline["lines"] if line["section_id"] == section["id"]
        ]
        vocal_duration = sum(
            max(0, min(line["end_ms"], end_ms) - max(line["start_ms"], start_ms))
            for line in section_lines
        )
        measurements[section["id"]] = {
            **loudness,
            **spectral,
            "loudness_profile_lufs": [round(value, 1) for value in loudness_profile],
            "beat_count": len(beats),
            "beat_density_per_minute": round(
                len(beats) / ((end_ms - start_ms) / 60_000), 1
            ),
            "vocal_coverage_ratio": round(vocal_duration / (end_ms - start_ms), 3),
        }

    baseline_segments: list[dict[str, Any]] = []
    feature_segments: list[dict[str, Any]] = []
    summary_segments: list[dict[str, Any]] = []
    previous_lufs: float | None = None
    assembly_started = time.perf_counter()

    for section in sections:
        section_lines = [
            line_payload(line, performer_names)
            for line in timeline["lines"]
            if line["section_id"] == section["id"]
        ]
        common = make_common_segment(section, section_lines)
        baseline_segments.append(common)

        measured = measurements[section["id"]]
        feature_segments.append(
            {
                **common,
                "perception": {
                    "kind": "acoustic_features",
                    "status": "automatic_unverified",
                    "features": measured,
                },
            }
        )

        instruments = overlapping_instruments(section, timeline["instrument_events"])
        performer_text = describe_performers(section_lines)
        instrument_text = (
            f"人工粗标注覆盖的乐器包括{'、'.join(instruments)}"
            if instruments
            else "现有人工乐器表没有为本段提供独立条目"
        )
        dynamic_text = describe_dynamics(
            measured["loudness_profile_lufs"], previous_lufs
        )
        summary_segments.append(
            {
                **common,
                "perception": {
                    "kind": "music_summary",
                    "status": "draft_needs_listening_review",
                    "summary": f"{performer_text}。{instrument_text}。{dynamic_text}。",
                },
            }
        )
        previous_lufs = measured["integrated_lufs"]

    envelope = {
        "schema_version": "0.1.0",
        "song_id": metadata["song_id"],
        "generated_from_audio_sha256": audio_sha256,
        "segment_unit": "song_section",
    }
    payloads = {
        "lyrics_only": {**envelope, "segments": baseline_segments},
        "candidate_a_features": {
            **envelope,
            "perception_notice": (
                "压缩声学指标不是原始音频，不能直接证明具体乐器或情绪。"
            ),
            "perception_provenance": {
                "loudness_and_spectrum": "automatic_ffmpeg_measurement",
                "beats": "automatic_unverified_reference",
                "vocal_coverage": "human_onsets_plus_estimated_vocal_ends",
            },
            "segments": feature_segments,
        },
        "candidate_b_summaries": {
            **envelope,
            "perception_notice": (
                "摘要来自人工标注与自动测量，不代表模型直接听见了原始音频。"
            ),
            "perception_provenance": {
                "performers_and_lyrics": "human_timeline_annotation",
                "instruments": "human_annotation_coarse",
                "dynamic_relation": "automatic_ffmpeg_measurement",
            },
            "segments": summary_segments,
        },
    }

    args.output.mkdir(parents=True, exist_ok=True)
    storage_bytes = {
        name: write_json(args.output / f"{name}.json", payload)
        for name, payload in payloads.items()
    }
    preprocessing_ms = round((time.perf_counter() - started) * 1000)
    payload_assembly_ms = round((time.perf_counter() - assembly_started) * 1000)
    baseline_cost = cumulative_cost(baseline_segments)
    metrics = {
        "schema_version": "0.1.0",
        "methodology": {
            "segments": len(sections),
            "unit": "song_section",
            "token_measurement": (
                "No provider tokenizer was available locally. The range uses "
                "UTF-8 bytes / 4 through bytes / 3 and is a comparison proxy, "
                "not billed token usage."
            ),
            "cumulative_cost": (
                "Sum of compact per-segment JSON responses; MCP tool definitions, "
                "protocol envelopes, user prompts, and model output are excluded."
            ),
            "audio_preprocessing": "offline FFmpeg; no network or model API calls",
        },
        "preprocessing_wall_ms": preprocessing_ms,
        "preprocessing_breakdown_ms": {
            "shared_loudness_measurement_used_by_a_and_b": round(
                loudness_measurement_seconds * 1000
            ),
            "candidate_a_only_spectral_measurement": round(
                spectral_measurement_seconds * 1000
            ),
            "payload_assembly_and_file_writes": payload_assembly_ms,
        },
        "variants": {
            name: {
                "pretty_json_storage_bytes": storage_bytes[name],
                "full_song_cumulative_response": cumulative_cost(payload["segments"]),
                "incremental_over_lyrics_only": {
                    key: value - baseline_cost[key]
                    for key, value in cumulative_cost(payload["segments"]).items()
                },
                "average_segment_response": {
                    key: round(value / len(payload["segments"]))
                    for key, value in cumulative_cost(payload["segments"]).items()
                },
            }
            for name, payload in payloads.items()
        },
    }
    write_json(args.output / "metrics.json", metrics)
    print(
        f"Built {len(sections)}-segment perception prototypes in "
        f"{preprocessing_ms} ms at {args.output.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
