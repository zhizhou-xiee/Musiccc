#!/usr/bin/env python3
"""Build review-only melody and harmony candidates for the JieYue MSS PoC.

This script deliberately keeps every machine-derived pitch, key, tempo, and
chord result in an unverified candidate state. It never edits the production
MCP data. Source audio and separated stems should remain outside the repo.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMELINE = ROOT / "data/songs/jieyue/mcp.json"
DEFAULT_OUTPUT = (
    ROOT
    / "data/songs/jieyue/experiments/melody-harmony-poc/outputs/candidates.json"
)
ANALYSIS_SR = 22_050
HOP_LENGTH = 256
FMIN = float(librosa.note_to_hz("C2"))
FMAX = float(librosa.note_to_hz("C6"))
PITCH_PROBABILITY_FLOOR = 0.60
CONTOUR_BINS = 16

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--vocals", type=Path, required=True)
    parser.add_argument("--accompaniment", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def finite_float(value: Any, digits: int = 4) -> float | None:
    number = float(value)
    return round(number, digits) if math.isfinite(number) else None


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) < 1e-8 or np.std(b) < 1e-8:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def note_name(midi: float) -> str:
    return str(librosa.midi_to_note(midi, octave=True, cents=False, unicode=False))


def flatten_timeline(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    lines: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    for segment in data["segments"]:
        sections[segment["id"]] = {
            "id": segment["id"],
            "title": segment["title"],
            "start_ms": segment["start_ms"],
            "end_ms": segment["end_ms"],
        }
        for line in segment.get("lyrics", []):
            lines.append({**line, "section_id": segment["id"], "section_title": segment["title"]})
    return lines, sections


def frame_slice(times: np.ndarray, start_ms: int, end_ms: int) -> np.ndarray:
    return (times >= start_ms / 1000) & (times <= end_ms / 1000)


def bin_pitch_points(
    times: np.ndarray,
    midi: np.ndarray,
    probability: np.ndarray,
    start_ms: int,
    end_ms: int,
    bins: int = CONTOUR_BINS,
) -> tuple[list[dict[str, Any]], float | None, float]:
    edges = np.linspace(start_ms, end_ms, bins + 1)
    valid_line = frame_slice(times, start_ms, end_ms)
    valid_pitch = valid_line & np.isfinite(midi) & (probability >= PITCH_PROBABILITY_FLOOR)
    baseline = float(np.nanmedian(midi[valid_pitch])) if np.any(valid_pitch) else None
    coverage = float(np.sum(valid_pitch) / max(1, np.sum(valid_line)))
    points: list[dict[str, Any]] = []

    for left, right in zip(edges[:-1], edges[1:], strict=True):
        mask = (
            (times * 1000 >= left)
            & (times * 1000 < right)
            & np.isfinite(midi)
            & (probability >= PITCH_PROBABILITY_FLOOR)
        )
        center_ms = int(round((left + right) / 2))
        if not np.any(mask) or baseline is None:
            points.append({"time_ms": center_ms, "midi": None, "relative_semitones": None, "note": None, "confidence": None})
            continue
        value = float(np.nanmedian(midi[mask]))
        confidence = float(np.nanmedian(probability[mask]))
        points.append(
            {
                "time_ms": center_ms,
                "midi": round(value, 2),
                "relative_semitones": round(value - baseline, 2),
                "note": note_name(value),
                "confidence": round(confidence, 3),
            }
        )
    return points, baseline, coverage


def dense_phrase_vector(
    times: np.ndarray,
    midi: np.ndarray,
    probability: np.ndarray,
    start_ms: int,
    end_ms: int,
    bins: int = 32,
) -> tuple[np.ndarray | None, float | None]:
    edges = np.linspace(start_ms, end_ms, bins + 1)
    values = np.full(bins, np.nan)
    for index, (left, right) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
        mask = (
            (times * 1000 >= left)
            & (times * 1000 < right)
            & np.isfinite(midi)
            & (probability >= PITCH_PROBABILITY_FLOOR)
        )
        if np.any(mask):
            values[index] = np.nanmedian(midi[mask])
    valid = np.flatnonzero(np.isfinite(values))
    if len(valid) < max(6, bins // 4):
        return None, None
    values = np.interp(np.arange(bins), valid, values[valid])
    median = float(np.median(values))
    return values - median, median


def key_candidates(chroma: np.ndarray) -> list[dict[str, Any]]:
    profile = np.mean(chroma, axis=1)
    candidates: list[dict[str, Any]] = []
    for root, name in enumerate(PITCH_CLASSES):
        for mode, source in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            score = correlation(profile, np.roll(source, root))
            candidates.append({"key": f"{name} {mode}", "score": round(score, 4)})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:5]


def chord_templates() -> list[tuple[str, np.ndarray]]:
    templates: list[tuple[str, np.ndarray]] = []
    for root, name in enumerate(PITCH_CLASSES):
        for suffix, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            template = np.zeros(12)
            template[[(root + interval) % 12 for interval in intervals]] = 1
            template /= np.linalg.norm(template)
            templates.append((f"{name}{suffix}", template))
    return templates


def harmony_windows(chroma: np.ndarray, chroma_times: np.ndarray, beat_times: np.ndarray) -> list[dict[str, Any]]:
    templates = chord_templates()
    windows: list[dict[str, Any]] = []
    # Four tracked beats per candidate window. This is a review aid, not meter inference.
    for index in range(0, max(0, len(beat_times) - 4), 4):
        start = float(beat_times[index])
        end = float(beat_times[index + 4])
        mask = (chroma_times >= start) & (chroma_times < end)
        if not np.any(mask):
            continue
        vector = np.mean(chroma[:, mask], axis=1)
        norm = np.linalg.norm(vector)
        if norm < 1e-8:
            continue
        vector /= norm
        scores = sorted(((name, float(np.dot(vector, template))) for name, template in templates), key=lambda item: item[1], reverse=True)
        margin = scores[0][1] - scores[1][1]
        status = "automatic_candidate" if margin >= 0.08 else "unknown_low_margin"
        windows.append(
            {
                "start_ms": int(round(start * 1000)),
                "end_ms": int(round(end * 1000)),
                "candidate": scores[0][0] if status == "automatic_candidate" else None,
                "alternate": scores[1][0],
                "top_score": round(scores[0][1], 4),
                "margin": round(margin, 4),
                "status": status,
            }
        )
    return windows


def main() -> None:
    args = parse_args()
    for source in (args.master, args.vocals, args.accompaniment, args.timeline):
        if not source.exists():
            raise SystemExit(f"Missing input: {source}")

    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    lines, sections = flatten_timeline(timeline)

    master, _ = librosa.load(args.master, sr=ANALYSIS_SR, mono=True)
    vocals, _ = librosa.load(args.vocals, sr=ANALYSIS_SR, mono=True)
    accompaniment, _ = librosa.load(args.accompaniment, sr=ANALYSIS_SR, mono=True)

    f0, voiced_flag, voiced_probability = librosa.pyin(
        vocals,
        fmin=FMIN,
        fmax=FMAX,
        sr=ANALYSIS_SR,
        frame_length=2048,
        hop_length=HOP_LENGTH,
    )
    midi = librosa.hz_to_midi(f0)
    frame_times = librosa.times_like(f0, sr=ANALYSIS_SR, hop_length=HOP_LENGTH)
    probability = np.where(voiced_flag, voiced_probability, 0.0)

    melody_lines: list[dict[str, Any]] = []
    line_lookup: dict[str, dict[str, Any]] = {}
    for line in lines:
        points, baseline, coverage = bin_pitch_points(
            frame_times,
            midi,
            probability,
            line["start_ms"],
            line["end_ms"],
        )
        voiced_values = [point["midi"] for point in points if point["midi"] is not None]
        item = {
            "line_id": line["id"],
            "section_id": line["section_id"],
            "section_title": line["section_title"],
            "text": line["text"],
            "start_ms": line["start_ms"],
            "end_ms": line["end_ms"],
            "performers": line["performers"],
            "status": "automatic_unverified",
            "method": "demucs_htdemucs_vocals_then_librosa_pyin",
            "voiced_coverage": round(coverage, 3),
            "baseline_midi": finite_float(baseline, 2) if baseline is not None else None,
            "candidate_range": {
                "lowest_note": note_name(min(voiced_values)) if voiced_values else None,
                "highest_note": note_name(max(voiced_values)) if voiced_values else None,
            },
            "contour_points": points,
        }
        melody_lines.append(item)
        line_lookup[line["id"]] = line

    repeated_pairs = [(f"line-{left:03d}", f"line-{right:03d}") for left, right in zip(range(19, 30), range(44, 55), strict=True)]
    relations: list[dict[str, Any]] = []
    for source_id, target_id in repeated_pairs:
        source = line_lookup[source_id]
        target = line_lookup[target_id]
        a, a_median = dense_phrase_vector(frame_times, midi, probability, source["start_ms"], source["end_ms"])
        b, b_median = dense_phrase_vector(frame_times, midi, probability, target["start_ms"], target["end_ms"])
        if a is None or b is None or a_median is None or b_median is None:
            relations.append({"source_line_id": source_id, "target_line_id": target_id, "status": "unknown_insufficient_pitch"})
            continue
        contour_correlation = correlation(a, b)
        relation = "strong_recurrence_candidate" if contour_correlation >= 0.80 else "possible_recurrence_candidate" if contour_correlation >= 0.60 else "uncertain"
        relations.append(
            {
                "source_line_id": source_id,
                "target_line_id": target_id,
                "status": "automatic_unverified",
                "relation": relation,
                "relative_contour_correlation": round(contour_correlation, 3),
                "median_pitch_shift_semitones": round(b_median - a_median, 2),
            }
        )

    harmonic_master = librosa.effects.harmonic(master)
    master_chroma = librosa.feature.chroma_cqt(y=harmonic_master, sr=ANALYSIS_SR, hop_length=512)
    keys = key_candidates(master_chroma)

    tempo, beat_frames = librosa.beat.beat_track(y=accompaniment, sr=ANALYSIS_SR, hop_length=512)
    beat_times = librosa.frames_to_time(beat_frames, sr=ANALYSIS_SR, hop_length=512)
    median_tempo = 60 / float(np.median(np.diff(beat_times))) if len(beat_times) > 1 else None

    harmonic_accompaniment = librosa.effects.harmonic(accompaniment)
    accompaniment_chroma = librosa.feature.chroma_cqt(y=harmonic_accompaniment, sr=ANALYSIS_SR, hop_length=512)
    chroma_times = librosa.times_like(accompaniment_chroma, sr=ANALYSIS_SR, hop_length=512)
    chords = harmony_windows(accompaniment_chroma, chroma_times, beat_times)

    output = {
        "schema_version": "melody-harmony-poc/0.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "song_id": timeline["song"]["id"],
        "production_integration": "none_review_only",
        "perception_notice": "所有旋律、调性、速度与和弦内容均为离线自动候选，未经人工校对；不代表接收模型直接听见原始音频。",
        "sources": {
            "master": {"basename": args.master.name, "repository_copy": False},
            "vocals_stem": {"basename": args.vocals.name, "repository_copy": False, "separation": "demucs_htdemucs_two_stems"},
            "accompaniment_stem": {"basename": args.accompaniment.name, "repository_copy": False, "separation": "demucs_htdemucs_two_stems"},
            "timeline_revision": timeline["revision"],
        },
        "analysis": {
            "sample_rate_hz": ANALYSIS_SR,
            "pitch": {"method": "librosa.pyin", "range": "C2-C6", "probability_floor": PITCH_PROBABILITY_FLOOR, "contour_bins_per_line": CONTOUR_BINS},
            "key": {"method": "mean_cqt_chroma_krumhansl_profile_correlation", "status": "automatic_unverified", "candidates": keys},
            "tempo": {
                "method": "librosa_beat_track_on_demucs_accompaniment",
                "status": "automatic_unverified",
                "aggregate_bpm": finite_float(np.asarray(tempo).reshape(-1)[0], 3),
                "median_beat_interval_bpm": finite_float(median_tempo, 3) if median_tempo is not None else None,
                "tracked_beats": int(len(beat_times)),
            },
            "meter": {"status": "unknown", "reason": "not_inferred_by_this_poc"},
            "harmony": {"method": "four_tracked_beat_mean_cqt_major_minor_triad_template", "status": "automatic_unverified", "candidate_margin_floor": 0.08},
        },
        "sections": list(sections.values()),
        "melody_lines": melody_lines,
        "relations": relations,
        "harmony_windows": chords,
        "review_policy": {
            "allowed_states": ["pending", "verified", "needs_correction", "unknown"],
            "rule": "Only reviewer-verified fields may be copied into a future MSS or MCP payload.",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Melody lines: {len(melody_lines)}")
    print(f"Repeat relations: {len(relations)}")
    print(f"Harmony windows: {len(chords)} ({sum(window['candidate'] is not None for window in chords)} above margin floor)")
    print(f"Top key candidate: {keys[0]['key']} ({keys[0]['score']})")
    print(f"Median beat-interval tempo: {finite_float(median_tempo, 3)} BPM")


if __name__ == "__main__":
    main()
