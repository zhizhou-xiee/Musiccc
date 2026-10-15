#!/usr/bin/env python3
"""Build a self-describing MSS/0.3 candidate from the reviewed MSS/0.2 data."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from build_mss_curve_poc import SECTION_CODES, sparse_keypoints


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "songs" / "jieyue" / "experiments" / "mss-curve-poc" / "outputs" / "mss.curves.json"
OUT = ROOT / "data" / "songs" / "jieyue" / "experiments" / "mss-v0.3-poc"

PLAIN_IDS = {
    "piano": "piano",
    "guitar": "guitar",
    "guzheng": "guzheng",
    "pipa": "pipa",
    "dizi": "dizi",
    "electronic_keyboard": "keyboard",
    "low_wind_family": "low_wind?",
    "low_string_or_bass_family": "low_strings_or_bass?",
    "drum_kit": "drums",
    "shaker_family": "shaker?",
    "gong_like_percussion": "gong_percussion?",
}

ENTER_ACTIONS = {
    "guitar_enter": ("background_enter", ["guitar"]),
    "guzheng_enter": ("foreground_enter", ["guzheng"]),
    "dizi_enter": ("foreground_enter", ["dizi"]),
    "electronic_keyboard_enter": ("background_enter", ["electronic_keyboard"]),
    "drums_enter": ("background_enter", ["drum_kit"]),
    "drums_enter_first": ("background_enter", ["drum_kit"]),
}

EXIT_ACTIONS = {
    "dizi_exit": ("foreground_exit", ["dizi"]),
    "guzheng_exit": ("foreground_exit", ["guzheng"]),
    "instruments_exit": ("background_exit", ["all"]),
    "other_instruments_exit": ("background_exit", ["other_instruments"]),
}

TAG_ACTIONS = {
    "guzheng_brief_harmony": "brief_harmony",
    "brief_harmony": "brief_harmony",
    "brief_rise": "brief_rise",
}

CURVE_CODES = {
    "loudness_rms_dbfs": "loudness",
    "spectral_centroid_hz": "centroid",
    "spectral_flux": "flux",
    "positive_energy_change_db": "onset_energy",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def names(values: list[str]) -> list[str]:
    return [PLAIN_IDS.get(value, value) for value in values]


def event_v03(event: dict[str, Any]) -> dict[str, Any]:
    layer = event["texture_layer"]
    result: dict[str, Any] = {
        "id": event["id"],
        "start_ms": event["start_ms"],
        "section": SECTION_CODES[event["section_id"]],
        "background": names(layer.get("background_instruments", [])),
        "foreground": names(layer.get("foreground_instruments", [])),
        "foreground_candidates": names(layer.get("foreground_candidates", [])),
        "background_enter": names(layer.get("background_additions", [])),
        "background_exit": [],
        "foreground_enter": [],
        "foreground_exit": [],
        "tags": [],
    }
    if event.get("end_ms") is not None:
        result["end_ms"] = event["end_ms"]

    for action in event.get("actions", []):
        if action in ENTER_ACTIONS:
            field, instruments = ENTER_ACTIONS[action]
            result[field] = unique(result[field] + names(instruments))
        elif action == "plucked_string_enter":
            result["foreground_enter"] = unique(
                result["foreground_enter"] + result["foreground_candidates"]
            )
        elif action == "light_percussion_enter":
            result["background_enter"] = unique(
                result["background_enter"] + names(["shaker_family", "drum_kit"])
            )
        elif action in EXIT_ACTIONS:
            field, instruments = EXIT_ACTIONS[action]
            result[field] = unique(result[field] + instruments)
        elif action in TAG_ACTIONS:
            result["tags"] = unique(result["tags"] + [TAG_ACTIONS[action]])
    return result


def compact_list(values: list[str]) -> str:
    return "+".join(values) if values else "-"


def compact_event(event: dict[str, Any]) -> str:
    timing = str(event["start_ms"])
    if event.get("end_ms") is not None:
        timing += f"-{event['end_ms']}"
    fields = [
        f"{timing}@{event['section']}",
        f"bg={compact_list(event['background'])}",
        f"fg={compact_list(event['foreground'])}",
    ]
    if event["foreground_candidates"]:
        fields.append(f"fg_candidates={compact_list(event['foreground_candidates'])}")
    for field in ("background_enter", "background_exit", "foreground_enter", "foreground_exit"):
        if event[field]:
            fields.append(f"{field}={compact_list(event[field])}")
    if event["tags"]:
        fields.append(f"tag={compact_list(event['tags'])}")
    return " ".join(fields)


def compact_curve(curve: dict[str, Any], sample_times: list[int]) -> str:
    points = sparse_keypoints(sample_times, curve["quantized"], target=8)
    values = ",".join(f"{time_ms}:{value}" for time_ms, value in points)
    return f"{CURVE_CODES[curve['id']]}={values}"


def nearest_curve_values(
    curve: dict[str, Any], sample_times: list[int], target_times: list[int]
) -> list[int | None]:
    values = curve["quantized"]
    result: list[int | None] = []
    for target_time in target_times:
        index = min(range(len(sample_times)), key=lambda item: abs(sample_times[item] - target_time))
        result.append(values[index])
    return result


def compact_v03(source: dict[str, Any]) -> str:
    """A small, self-contained matrix; no event points to another event."""
    sample_times = source["sampling"]["sample_times_ms"]
    target_times = [1750, 37750, 74750, 109750, 145750, 181750, 217750, 249594]
    curves = {CURVE_CODES[item["id"]]: item for item in source["curves"]}

    def curve_row(curve_id: str) -> str:
        values = nearest_curve_values(curves[curve_id], sample_times, target_times)
        return curve_id + "=" + ",".join("?" if value is None else str(value) for value in values)

    return "\n".join(
        [
            "MSS/0.3 借月249.594s；事实层；无情绪/比喻；未听原音；曲线自动未校",
            "曲线=全曲p02-p98→0..63；秒=" + ",".join(f"{time_ms / 1000:g}" for time_ms in target_times),
            curve_row("loudness").replace("loudness", "响") + "；" + curve_row("centroid").replace("centroid", "质"),
            curve_row("flux").replace("flux", "变") + "；" + curve_row("onset_energy").replace("onset_energy", "起"),
            "响=响度,质=频谱质心,变=频谱变化,起=起音能量；bg=持续基底,fg=当前前景,?=不确定；p钢琴,g吉他,z古筝,a琵琶,d横笛,k电子琴,w低沉吹奏?,l低音提琴类?,r架子鼓,s沙鼓?,o锣鼓点?",
            "53.285 bg:g,fg:z",
            "58.795 bg:w+l+k,fg:z",
            "64.100 bg:w+l+k+s+r,fg:z,tag:短和声",
            "74.316 bg:w+l+k,fg:z;86.243 bg:l+k+r,fg:z",
            "109.358-119.138 bg:w+l+k+r,fg:d",
            "119.138 bg:w+l+k+r;前景:横笛退出,(古筝|琵琶)?进入",
            "152.761,158.631 bg:l+k,fg:z",
            "190.860-210.250 bg:l+k+r;193.668 fg:k",
            "195.413 bg:l+k+r,fg:z,tag:短和声",
            "199.360-200.450 bg:l+k+r,fg:z,tag:短扬,与195.413不同事件",
            "210.250 bg:-;235.060 bg:l+k+r,fg:z",
            "242.489 bg:l+k+r;前景:古筝退出,吉他进入",
            "unknown=旋律轮廓+调性+拍号",
        ]
    )


def token_proxy(text: str) -> dict[str, int]:
    byte_count = len(text.encode("utf-8"))
    return {
        "utf8_bytes": byte_count,
        "unicode_characters": len(text),
        "estimated_tokens_low": math.ceil(byte_count / 4),
        "estimated_tokens_high": math.ceil(byte_count / 3),
    }


def main() -> None:
    source = read_json(SOURCE)
    events = [event_v03(event) for event in source["events"]]
    sample_times = source["sampling"]["sample_times_ms"]
    full = {
        "mss_version": "0.3",
        "track": source["track"],
        "policy": {
            "facts_only": True,
            "emotion_labels": False,
            "metaphors": False,
            "audio_heard_by_receiver": False,
            "automatic_curves_verified": False,
        },
        "events": events,
        "curves": [
            {
                "id": CURVE_CODES[curve["id"]],
                "status": curve["status"],
                "quantization": "song_percentile_2_98_to_0_63",
                "keypoints": sparse_keypoints(sample_times, curve["quantized"], target=8),
            }
            for curve in source["curves"]
        ],
        "unknown": ["melody_contour", "key", "meter"],
        "source_ids": ["project_lead_listening_notes", "final_mp3_offline_measurement"],
    }
    compact = compact_v03(source)
    metrics = {
        "mss_version": "0.3",
        "source": str(SOURCE.relative_to(ROOT)),
        "network_calls": 0,
        "model_api_calls": 0,
        "event_count": len(events),
        "curve_keypoints": 8,
        "compact": token_proxy(compact),
        "acceptance_targets": {
            "actual_music_payload_tokens_max": 800,
            "objective_mean_min": 9.1667,
            "unsupported_factual_claims_max": 1,
        },
    }
    write_json(OUT / "outputs" / "mss.v03.json", full)
    write_text(OUT / "outputs" / "mss_v03_800.txt", compact)
    write_json(OUT / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
