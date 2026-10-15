#!/usr/bin/env python3
"""Build the JieYue MSS/0.2 curve-first proof of concept.

The script is deliberately offline and dependency-light. FFmpeg decodes the
registered MP3 master and measures spectral frames; Python's standard library
computes RMS, energy-change and adaptive sparse keypoints. It does not infer
emotion, key, meter, instruments, or a melody line from the mixed master.
"""

from __future__ import annotations

import argparse
import array
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
POC_DIR = SONG_DIR / "experiments" / "mss-curve-poc"
OUTPUT_DIR = POC_DIR / "outputs"
TIMELINE_PATH = SONG_DIR / "timeline.reference.json"
DETAIL_PATH = SONG_DIR / "source" / "detailed-listening-annotations.json"
OLD_NATURAL_PATH = SONG_DIR / "experiments" / "mss-poc" / "outputs" / "natural_800.txt"

SAMPLE_RATE = 8_000
WINDOW_MS = 500
SHORT_FRAME_MS = 20
QUANT_LEVELS = 64
TARGET_KEYPOINTS = 16

SECTION_CODES = {
    "a_cappella": "ac", "intro": "in", "verse_1": "v1", "pre_chorus_1": "p1",
    "chorus_1": "c1", "interlude": "it", "verse_2": "v2", "pre_chorus_2": "p2",
    "chorus_2": "c2", "bridge": "br", "final_chorus": "fc", "outro": "ou",
}

INSTRUMENT_CODES = {
    "piano": "pn", "guitar": "gt", "guzheng": "gz", "pipa": "pp", "dizi": "fl",
    "electronic_keyboard": "ek", "low_wind_family": "lw?",
    "low_string_or_bass_family": "lb?", "drum_kit": "dr", "shaker_family": "sh?",
    "gong_like_percussion": "gp?",
}

INSTRUMENT_NAMES_ZH = {
    "piano": "钢琴", "guitar": "吉他", "guzheng": "古筝", "pipa": "琵琶", "dizi": "横笛",
    "electronic_keyboard": "电子琴", "low_wind_family": "低沉吹奏类?",
    "low_string_or_bass_family": "低音弦乐类?", "drum_kit": "架子鼓", "shaker_family": "沙鼓类?",
    "gong_like_percussion": "锣鼓类?",
}

ACTION_NAMES_ZH = {
    "guitar_enter": "吉他入", "guzheng_enter": "古筝入", "guzheng_brief_harmony": "古筝短和声",
    "light_percussion_enter": "轻打击入", "drums_enter_first": "鼓先入", "instruments_exit": "伴奏退",
    "dizi_enter": "横笛入", "dizi_exit": "横笛退", "plucked_string_enter": "拨弦入",
    "other_instruments_exit": "其他乐器退", "electronic_keyboard_enter": "电子琴入",
    "brief_harmony": "短和声", "brief_rise": "短扬起", "drums_enter": "鼓入", "guzheng_exit": "古筝退",
}

CURVE_CODES = {
    "loudness_rms_dbfs": "L",
    "spectral_centroid_hz": "C",
    "spectral_flux": "F",
    "positive_energy_change_db": "O",
}

SPECTRAL_RE = re.compile(
    r"lavfi\.aspectralstats\.\d+\.(centroid|flux|rolloff)=([^\s]+)"
)
PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_mono(audio_path: Path) -> array.array[float]:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(audio_path),
        "-af", "aformat=channel_layouts=mono", "-ar", str(SAMPLE_RATE),
        "-f", "f32le", "-acodec", "pcm_f32le", "-",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    samples = array.array("f")
    samples.frombytes(result.stdout)
    if samples.itemsize != 4:
        raise RuntimeError("Unexpected float sample width")
    return samples


def spectral_frames(audio_path: Path) -> list[dict[str, float]]:
    command = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path), "-af",
        (
            f"aformat=channel_layouts=mono,aresample={SAMPLE_RATE},"
            "aspectralstats=win_size=1024:measure=centroid+flux+rolloff,"
            "ametadata=print"
        ),
        "-f", "null", "-",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    frames: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in result.stderr.splitlines():
        pts_match = PTS_RE.search(line)
        if pts_match:
            if current and {"centroid", "flux", "rolloff"} <= current.keys():
                frames.append(current)
            current = {"time_ms": round(float(pts_match.group(1)) * 1000)}
            continue
        spectral_match = SPECTRAL_RE.search(line)
        if current is not None and spectral_match:
            try:
                current[spectral_match.group(1)] = float(spectral_match.group(2))
            except ValueError:
                pass
    if current and {"centroid", "flux", "rolloff"} <= current.keys():
        frames.append(current)
    if not frames:
        raise RuntimeError("FFmpeg returned no spectral frames")
    return frames


def dbfs_from_sumsq(sumsq: float, count: int) -> float:
    if count <= 0 or sumsq <= 1e-18:
        return -96.0
    return max(-96.0, 20 * math.log10(math.sqrt(sumsq / count)))


def measure_energy(samples: array.array[float], duration_ms: int) -> tuple[list[int], list[float], list[float]]:
    window_samples = round(SAMPLE_RATE * WINDOW_MS / 1000)
    short_samples = round(SAMPLE_RATE * SHORT_FRAME_MS / 1000)
    sample_times: list[int] = []
    loudness_values: list[float] = []
    energy_change_values: list[float] = []
    previous_short_db: float | None = None

    for window_start in range(0, len(samples), window_samples):
        window_end = min(len(samples), window_start + window_samples)
        if window_end <= window_start:
            break
        sumsq = 0.0
        positive_changes: list[float] = []
        for short_start in range(window_start, window_end, short_samples):
            short_end = min(window_end, short_start + short_samples)
            short_sumsq = 0.0
            for value in samples[short_start:short_end]:
                squared = value * value
                sumsq += squared
                short_sumsq += squared
            short_db = dbfs_from_sumsq(short_sumsq, short_end - short_start)
            if previous_short_db is not None:
                positive_changes.append(max(0.0, short_db - previous_short_db))
            previous_short_db = short_db
        center_ms = min(duration_ms, round((window_start + (window_end - window_start) / 2) / SAMPLE_RATE * 1000))
        sample_times.append(center_ms)
        loudness_values.append(round(dbfs_from_sumsq(sumsq, window_end - window_start), 2))
        energy_change_values.append(round(statistics.mean(positive_changes) if positive_changes else 0.0, 3))
    return sample_times, loudness_values, energy_change_values


def aggregate_spectral(
    frames: list[dict[str, float]], sample_times: list[int]
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    buckets: list[list[dict[str, float]]] = [[] for _ in sample_times]
    for frame in frames:
        index = min(len(sample_times) - 1, max(0, int(frame["time_ms"] // WINDOW_MS)))
        buckets[index].append(frame)

    def values_for(key: str, digits: int) -> list[float | None]:
        result: list[float | None] = []
        for bucket in buckets:
            values = [item[key] for item in bucket if math.isfinite(item[key])]
            result.append(round(statistics.median(values), digits) if values else None)
        return result

    return values_for("centroid", 1), values_for("flux", 4), values_for("rolloff", 1)


def percentile(values: list[float], position: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = (len(ordered) - 1) * position
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def quantize(values: list[float | None]) -> tuple[list[int | None], dict[str, Any]]:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    low = percentile(finite, 0.02)
    high = percentile(finite, 0.98)
    if high <= low:
        high = low + 1.0
    quantized: list[int | None] = []
    for value in values:
        if value is None or not math.isfinite(value):
            quantized.append(None)
        else:
            clipped = max(low, min(high, value))
            quantized.append(round((clipped - low) / (high - low) * (QUANT_LEVELS - 1)))
    return quantized, {
        "method": "song_percentile_2_98_clipped_linear",
        "levels": QUANT_LEVELS,
        "physical_low": round(low, 4),
        "physical_high": round(high, 4),
        "missing": None,
    }


def point_distance(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> float:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    if x1 == x2 and y1 == y2:
        return math.hypot(x - x1, y - y1)
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def rdp(points: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    if len(points) <= 2:
        return points
    start, end = points[0], points[-1]
    max_distance = -1.0
    max_index = 0
    for index in range(1, len(points) - 1):
        distance = point_distance(points[index], start, end)
        if distance > max_distance:
            max_distance = distance
            max_index = index
    if max_distance > epsilon:
        left = rdp(points[: max_index + 1], epsilon)
        right = rdp(points[max_index:], epsilon)
        return left[:-1] + right
    return [start, end]


def sparse_keypoints(sample_times: list[int], values: list[int | None], target: int = TARGET_KEYPOINTS) -> list[list[int]]:
    valid = [(time_ms, value) for time_ms, value in zip(sample_times, values) if value is not None]
    if len(valid) <= target:
        return [[time_ms, value] for time_ms, value in valid]
    time_scale = max(1.0, (sample_times[-1] - sample_times[0]) / 63)
    scaled = [(round(time_ms / time_scale), value) for time_ms, value in valid]
    epsilon = 0.5
    simplified = scaled
    while len(simplified) > target and epsilon < 1024:
        epsilon *= 1.28
        simplified = rdp(scaled, epsilon)
    original_for_scaled: dict[tuple[int, int], tuple[int, int]] = {}
    for original_point, scaled_point in zip(valid, scaled):
        original_for_scaled[scaled_point] = original_point
    deduplicated = list(dict.fromkeys(simplified))
    return [[*original_for_scaled[point]] for point in deduplicated]


def curve_payload(
    curve_id: str,
    label_zh: str,
    unit: str,
    sample_times: list[int],
    values: list[float | None],
    measurement: str,
) -> dict[str, Any]:
    quantized, normalization = quantize(values)
    return {
        "id": curve_id,
        "label_zh": label_zh,
        "status": "automatic_unverified",
        "unit": unit,
        "window_ms": WINDOW_MS,
        "hop_ms": WINDOW_MS,
        "measurement": measurement,
        "values": values,
        "quantized": quantized,
        "normalization": normalization,
        "sparse_keypoints": sparse_keypoints(sample_times, quantized),
        "source_ids": ["final_mp3_offline_measurement"],
    }


def event_code(event: dict[str, Any]) -> str:
    instruments = [INSTRUMENT_CODES.get(item, item) for item in event.get("instruments", [])]
    candidates = [INSTRUMENT_CODES.get(item, item) for item in event.get("instrument_candidates", [])]
    if candidates:
        instruments.append("(" + "|".join(candidates) + ")?")
    payload = "+".join(instruments) or "-"
    if event.get("foreground"):
        payload += ">" + INSTRUMENT_CODES.get(event["foreground"], event["foreground"])
    if event.get("actions"):
        payload += ":" + ",".join(event["actions"])
    return payload


def curve_line(curve: dict[str, Any]) -> str:
    points = ",".join(f"{time_ms}:{value}" for time_ms, value in curve["sparse_keypoints"])
    normalization = curve["normalization"]
    return (
        f"C {CURVE_CODES[curve['id']]} q0..63 phys={normalization['physical_low']:g}.."
        f"{normalization['physical_high']:g}{curve['unit']} kp={points}"
    )


def token_proxy(text: str) -> dict[str, int]:
    byte_count = len(text.encode("utf-8"))
    return {
        "utf8_bytes": byte_count,
        "unicode_characters": len(text),
        "estimated_tokens_low": math.ceil(byte_count / 4),
        "estimated_tokens_high": math.ceil(byte_count / 3),
    }


def build_compact(mss: dict[str, Any]) -> str:
    sections = ";".join(
        f"{SECTION_CODES[section['id']]}:{section['start_ms']}-{section['end_ms']}"
        for section in mss["sections"]
    )
    events = ";".join(
        f"{event['start_ms']}@{SECTION_CODES[event['section_id']]}={event_code(event)}"
        for event in mss["events"]
    )
    curve_lines = [curve_line(curve) for curve in mss["curves"]]
    return "\n".join(
        [
            f"MSS/0.2 TRACK=jieyue D={mss['track']['duration_ms']}ms",
            "NOTICE facts+automatic curves; no emotion/metaphor; not raw-audio hearing",
            "Q each curve p02..p98=>0..63; kp=adaptive keypoints; ~=missing; L=loudness C=centroid F=flux O=energy-onset",
            "I pn=piano gt=guitar gz=guzheng pp=pipa fl=dizi ek=keyboard lw?=low-wind lb?=low-bass dr=drums sh?=shaker gp?=gong-perc",
            f"S {sections}",
            *curve_lines,
            "G conductor-proxy=[L,dL,F,C] vector; no scalar average; no real conductor data",
            f"E {events}",
            "U melody=unknown(mixed master; no reliable separation); meter/key=unknown",
        ]
    )


def build_curve_natural_baseline(mss: dict[str, Any]) -> str:
    lines = [
        "《借月》客观曲线文字基线。下列数据来自最终 MP3 的离线自动测量，未经人工核验；不包含情绪词，也不表示模型听到了音频。",
        "每条曲线先按全曲第2至第98百分位裁剪，再量化到0至63。以下只列自适应保留的形状关键点，格式为毫秒:数值。",
    ]
    for curve in mss["curves"]:
        points = "、".join(f"{time_ms}:{value}" for time_ms, value in curve["sparse_keypoints"])
        lines.append(f"{curve['label_zh']}：{points}。")
    lines.append("旋律轮廓未知：当前只有混合母带，没有可靠的主旋律分离或经人工核验的音符转录。")
    return "\n".join(lines)


def build_natural_hybrid(mss: dict[str, Any]) -> str:
    """Natural-language wrapper around the same compact evidence as MSS/0.2."""
    lines = [
        "《借月》客观文字+曲线对照。自动曲线未核验；不含情绪或比喻；不表示模型听到音频。曲线按全曲p02–p98量化为0–63，列稀疏关键点（毫秒:值）。",
    ]
    for curve in mss["curves"]:
        points = ",".join(f"{time_ms}:{value}" for time_ms, value in curve["sparse_keypoints"])
        lines.append(f"{curve['label_zh']}={points}")

    event_parts = []
    for event in mss["events"]:
        instruments = [INSTRUMENT_NAMES_ZH[item] for item in event.get("instruments", [])]
        candidates = [INSTRUMENT_NAMES_ZH[item].rstrip("?") for item in event.get("instrument_candidates", [])]
        if candidates:
            instruments.append("或".join(candidates) + "?")
        payload = "、".join(instruments)
        foreground = event.get("foreground")
        if foreground:
            payload += f"(前景{INSTRUMENT_NAMES_ZH[foreground]})"
        actions = [ACTION_NAMES_ZH.get(item, item) for item in event.get("actions", [])]
        if actions:
            payload += ("；" if payload else "") + "、".join(actions)
        event_parts.append(f"{event['start_ms']}:{payload or event['type']}")
    lines.append("事件=" + ";".join(event_parts))
    lines.append("旋律=未知（混合母带无可靠分离）；拍号/调性=未知。")
    return "\n".join(lines)


def extrema_probes(sample_times: list[int], curves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {curve["id"]: curve for curve in curves}
    loudness = by_id["loudness_rms_dbfs"]["values"]
    flux = by_id["spectral_flux"]["values"]
    centroid = by_id["spectral_centroid_hz"]["values"]
    loud_deltas = [0.0] + [round(loudness[index] - loudness[index - 1], 2) for index in range(1, len(loudness))]
    active_pairs = [
        index for index in range(1, len(loud_deltas))
        if loudness[index - 1] > -50 and loudness[index] > -50
    ]
    rise_index = max(active_pairs, key=lambda index: loud_deltas[index])
    fall_index = min(active_pairs, key=lambda index: loud_deltas[index])
    peak_loudness_index = max(range(len(loudness)), key=lambda index: loudness[index])
    peak_flux_index = max(range(len(flux)), key=lambda index: flux[index] if flux[index] is not None else -math.inf)
    peak_centroid_index = max(range(len(centroid)), key=lambda index: centroid[index] if centroid[index] is not None else -math.inf)
    return [
        {
            "id": "fastest_loudness_rise",
            "question": "排除静音到有声的边界后，哪一个 500ms 窗口的 RMS 响度上升最快？",
            "ground_truth": {"time_ms": sample_times[rise_index], "delta_db": loud_deltas[rise_index]},
            "metric": "exact_window_or_within_one_hop",
        },
        {
            "id": "fastest_loudness_fall",
            "question": "排除有声到静音的边界后，哪一个 500ms 窗口的 RMS 响度下降最快？",
            "ground_truth": {"time_ms": sample_times[fall_index], "delta_db": loud_deltas[fall_index]},
            "metric": "exact_window_or_within_one_hop",
        },
        {
            "id": "peak_loudness",
            "question": "全曲 RMS 响度最高的 500ms 窗口在哪里？",
            "ground_truth": {"time_ms": sample_times[peak_loudness_index], "dbfs": loudness[peak_loudness_index]},
            "metric": "exact_window_or_within_one_hop",
        },
        {
            "id": "peak_spectral_flux",
            "question": "频谱变化量最高的窗口在哪里？",
            "ground_truth": {"time_ms": sample_times[peak_flux_index], "value": flux[peak_flux_index]},
            "metric": "exact_window_or_within_one_hop",
        },
        {
            "id": "peak_spectral_centroid",
            "question": "频谱质心最高的窗口在哪里？",
            "ground_truth": {"time_ms": sample_times[peak_centroid_index], "hz": centroid[peak_centroid_index]},
            "metric": "exact_window_or_within_one_hop",
        },
    ]


def build_mss(
    timeline: dict[str, Any],
    details: dict[str, Any],
    sample_times: list[int],
    curves: list[dict[str, Any]],
) -> dict[str, Any]:
    duration = timeline["timeline_timebase"]["duration_ms"]
    sections = [
        {
            "id": section["id"],
            "label": section["title"],
            "start_ms": section["start_ms"],
            "end_ms": min(section["end_ms"], duration),
            "lyric_line_ids": section["line_ids"],
        }
        for section in timeline["sections"]
        if "audio" in section["media"] and section["start_ms"] < duration
    ]
    events = [{**event, "source_ids": ["project_lead_listening_notes"]} for event in details["events"]]
    return {
        "mss_version": "0.2",
        "representation_kind": "objective_events_plus_multivariate_time_series",
        "interpretation_policy": {
            "default_layer": "absent",
            "excluded_from_core": ["emotion_label", "mood", "metaphor", "listener_reaction"],
            "reason": "Core MSS preserves observable change while leaving interpretation to the receiving model.",
        },
        "track": {
            "song_id": timeline["song_id"],
            "title": timeline["title"],
            "duration_ms": duration,
            "audio_sha256": timeline["timeline_timebase"]["sha256"],
        },
        "sampling": {
            "sample_times_ms": sample_times,
            "window_ms": WINDOW_MS,
            "hop_ms": WINDOW_MS,
            "short_energy_frame_ms": SHORT_FRAME_MS,
        },
        "sections": sections,
        "lyrics": timeline["lines"],
        "performers": timeline["performers"],
        "instrument_vocabulary": details["vocabulary"],
        "events": events,
        "curves": curves,
        "gesture_proxy": {
            "status": "derived_experimental",
            "kind": "multichannel_vector_not_scalar",
            "channels": [
                "loudness_rms_dbfs",
                "first_difference_of_loudness",
                "spectral_flux",
                "spectral_centroid_hz",
            ],
            "note": "受指挥手势启发的读取方式；没有实际指挥数据，也不把不同维度平均为单一曲线。",
        },
        "unknowns": [
            {
                "id": "melody_contour",
                "status": "unknown",
                "reason": "混合母带没有可靠主旋律分离或经人工核验的音符转录；不以频谱质心冒充旋律。",
            },
            {"id": "meter", "status": "unknown", "reason": "拍号尚未可靠识别。"},
            {"id": "key", "status": "unknown", "reason": "调性尚未可靠识别。"},
        ],
        "sources": [
            {
                "id": "final_mp3_offline_measurement",
                "kind": "automatic_audio_measurement",
                "status": "automatic_unverified",
                "description": "最终 MP3 母带经本地 FFmpeg 与确定性标准库计算；没有网络或模型 API 调用。",
            },
            {
                "id": "project_lead_listening_notes",
                "kind": "human_listening_annotation",
                "status": "human_annotated",
                "description": "项目负责人提供的乐器、动作、音区与进入退出记录。",
            },
            {
                "id": "timeline_reference",
                "kind": "human_timeline_with_estimated_vocal_ends",
                "status": "mixed_precision",
                "description": "歌词开口、估算唱完、演唱者与段落时间轴。",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=POC_DIR)
    args = parser.parse_args()
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")
    if not args.audio.is_file():
        raise SystemExit(f"Audio file not found: {args.audio}")

    started = time.perf_counter()
    timeline = read_json(TIMELINE_PATH)
    details = read_json(DETAIL_PATH)
    expected_hash = timeline["timeline_timebase"]["sha256"]
    actual_hash = sha256_file(args.audio)
    if actual_hash != expected_hash:
        raise SystemExit(f"Audio SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")

    duration = timeline["timeline_timebase"]["duration_ms"]
    decode_started = time.perf_counter()
    samples = decode_mono(args.audio)
    sample_times, loudness, energy_change = measure_energy(samples, duration)
    decode_ms = round((time.perf_counter() - decode_started) * 1000)

    spectral_started = time.perf_counter()
    frames = spectral_frames(args.audio)
    centroid, flux, rolloff = aggregate_spectral(frames, sample_times)
    # Spectral statistics on near-silence are numerical artifacts rather than
    # meaningful timbre evidence. Keep those windows explicitly missing.
    for index, loudness_db in enumerate(loudness):
        if loudness_db <= -55:
            centroid[index] = None
            flux[index] = None
            rolloff[index] = None
    spectral_ms = round((time.perf_counter() - spectral_started) * 1000)

    curves = [
        curve_payload(
            "loudness_rms_dbfs", "RMS 响度", "dBFS", sample_times, loudness,
            "mono 8kHz; 500ms RMS; floor -96dBFS",
        ),
        curve_payload(
            "spectral_centroid_hz", "频谱质心", "Hz", sample_times, centroid,
            "FFmpeg aspectralstats centroid; per-window median",
        ),
        curve_payload(
            "spectral_flux", "频谱变化量", "ratio", sample_times, flux,
            "FFmpeg aspectralstats flux; per-window median",
        ),
        curve_payload(
            "positive_energy_change_db", "正向能量变化", "dB_per_20ms", sample_times, energy_change,
            "mean positive RMS dB difference across 20ms frames in each 500ms window",
        ),
    ]

    mss = build_mss(timeline, details, sample_times, curves)
    output_dir = args.output / "outputs"
    write_json(output_dir / "mss.curves.json", mss)
    compact = build_compact(mss)
    natural_curve = build_curve_natural_baseline(mss)
    natural_hybrid = build_natural_hybrid(mss)
    write_text(output_dir / "mss_curve_800.txt", compact)
    write_text(output_dir / "natural_curve_800.txt", natural_curve)
    write_text(output_dir / "natural_hybrid_800.txt", natural_hybrid)
    if OLD_NATURAL_PATH.is_file():
        write_text(output_dir / "natural_event_baseline_800.txt", OLD_NATURAL_PATH.read_text(encoding="utf-8"))

    probes = extrema_probes(sample_times, curves)
    rubric = {
        "evaluation_kind": "curve_fidelity_and_interpretive_freedom",
        "warning": "尚未调用任何模型。自由回答的差异不自动等于理解更好，必须同时检查客观曲线忠实度。",
        "objective_probes": probes,
        "free_interpretation_prompts": [
            {
                "id": "whole_song_motion",
                "prompt": "只依据所给音乐事实与曲线，描述你观察到的音乐运动，并自由选择比喻；明确区分观测与联想。",
            },
            {
                "id": "contrast_two_windows",
                "prompt": "选择两个曲线运动明显不同的时间窗口，先陈述可核对的差异，再给出你自己的理解。",
            },
        ],
        "scoring": {
            "objective_accuracy": "时间窗、方向、峰谷与同步变化是否符合曲线。",
            "hallucination_rate": "是否声称输入中没有的乐器、旋律、调性或情绪事实。",
            "interpretation_diversity": "多次回答的联想差异；只作辅助指标。",
            "observation_interpretation_separation": "是否把测量事实与自主联想明确分开。",
        },
    }
    write_json(args.output / "evaluation-rubric.json", rubric)

    variants = {
        "mss_curve_800": compact,
        "natural_curve_800": natural_curve,
        "natural_hybrid_800": natural_hybrid,
    }
    if OLD_NATURAL_PATH.is_file():
        variants["natural_event_baseline_800"] = OLD_NATURAL_PATH.read_text(encoding="utf-8")
    metrics = {
        "schema_version": "0.2.0",
        "audio_sha256": actual_hash,
        "preprocessing": {
            "total_wall_ms": round((time.perf_counter() - started) * 1000),
            "decode_and_energy_ms": decode_ms,
            "spectral_measurement_ms": spectral_ms,
            "network_calls": 0,
            "model_api_calls": 0,
            "paid_resources_created": 0,
        },
        "curve_sampling": {
            "windows": len(sample_times),
            "window_ms": WINDOW_MS,
            "hop_ms": WINDOW_MS,
            "curves": len(curves),
            "sparse_keypoints": {curve["id"]: len(curve["sparse_keypoints"]) for curve in curves},
        },
        "storage": {
            "input_audio_bytes": args.audio.stat().st_size,
            "mss_curves_pretty_json_bytes": (output_dir / "mss.curves.json").stat().st_size,
            "mss_curve_800_bytes": (output_dir / "mss_curve_800.txt").stat().st_size,
            "natural_hybrid_800_bytes": (output_dir / "natural_hybrid_800.txt").stat().st_size,
        },
        "token_notice": "UTF-8 bytes / 4 through bytes / 3 proxy only; no provider tokenizer or billed model call.",
        "variants": {name: token_proxy(value) for name, value in variants.items()},
        "event_integrity": {
            "source_events": len(details["events"]),
            "mss_events": len(mss["events"]),
            "stable_ids_preserved": [event["id"] for event in details["events"]] == [event["id"] for event in mss["events"]],
            "guzheng_related_event_times_ms": [
                event["start_ms"] for event in details["events"]
                if "guzheng" in event.get("instruments", []) or "guzheng" in event.get("instrument_candidates", [])
                or "guzheng_exit" in event.get("actions", [])
            ],
            "source_ambiguity": "项目负责人原文在 195413 ms 两次提到古筝短暂和声/扬起；当前合并为一个事件。如实际为两次，需要第二个时间戳。",
        },
    }
    write_json(args.output / "metrics.json", metrics)
    print(f"Built MSS/0.2: {len(sample_times)} windows, {len(curves)} curves, {len(mss['events'])} events")
    for name, measured in metrics["variants"].items():
        print(f"{name}: {measured['utf8_bytes']} bytes, proxy {measured['estimated_tokens_low']}-{measured['estimated_tokens_high']} tokens")
    print(f"Preprocessing: {metrics['preprocessing']['total_wall_ms']} ms")


if __name__ == "__main__":
    main()
