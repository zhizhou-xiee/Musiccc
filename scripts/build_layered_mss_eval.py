#!/usr/bin/env python3
"""Build reproducible blind-test packets for the layered MSS comparison."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SONG = ROOT / "data" / "songs" / "jieyue"
OUT = SONG / "experiments" / "layered-mss-eval"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def size(text: str) -> dict[str, int]:
    byte_count = len(text.encode("utf-8"))
    return {
        "utf8_bytes": byte_count,
        "estimated_tokens_low": math.ceil(byte_count / 4),
        "estimated_tokens_high": math.ceil(byte_count / 3),
    }


def lyric_context(timeline: dict[str, Any]) -> str:
    performers = {item["id"]: item["display_name"] for item in timeline["performers"]}
    lines = [
        "《借月》共享歌词时间轴。以下只有歌词、演唱者和时间，不包含乐器、曲线或情绪判断。",
    ]
    for line in timeline["lines"]:
        names = "、".join(performers[item["id"]] for item in line["performers"])
        lines.append(f"{line['start_ms']}-{line['end_ms']} {names}：{line['text']}")
    return "\n".join(lines)


def questions() -> dict[str, Any]:
    return {
        "instructions": "只依据收到的材料作答。材料没有支持时写 unknown，不要凭常识或措辞猜测。每题分开回答，并区分材料中的事实与自己的推断。",
        "objective": [
            {"id": "layer_053285", "question": "53.285 秒古筝出现时，持续基底是什么？古筝处于哪一层？", "ground_truth": "吉他为持续基底；古筝为短暂前景和声。"},
            {"id": "layer_058795", "question": "58.795 秒古筝短和声之下有哪些持续基底？", "ground_truth": "低沉吹奏类、低音提琴类、电子琴。"},
            {"id": "layer_064100", "question": "64.100 秒前景与基底分别发生了什么？", "ground_truth": "古筝在前景作副高音区短和声；原低沉吹奏/低音提琴类/电子琴基底继续，沙鼓类与轻架子鼓加入基底。"},
            {"id": "layer_119138", "question": "119.138 秒前景如何交接？交接后哪些基底继续？", "ground_truth": "横笛退出，古筝或琵琶候选进入前景；低沉吹奏类、低音提琴类、电子琴、架子鼓继续作基底。"},
            {"id": "uncertainty_119138", "question": "119.138 秒进入前景的拨弦乐器是否已经确定？", "ground_truth": "没有确定；候选为古筝或琵琶。"},
            {"id": "layer_prechorus2", "question": "152.761 与 158.631 秒两次古筝亮音之下的基底是什么？", "ground_truth": "低音提琴类与电子琴持续作基底。"},
            {"id": "layer_bridge", "question": "195.413 秒与 199.360–200.450 秒是同一次古筝事件吗？它们之下的基底是什么？", "ground_truth": "不是；前者为短暂和声，后者为两句歌词间的短暂扬起定位窗口。两者下方均持续低音提琴类、电子琴、架子鼓基底。"},
            {"id": "layer_outro", "question": "235.060 秒古筝来到前景时，底层是否只剩古筝？", "ground_truth": "不是；低音提琴类、电子琴和架子鼓仍作基底。"},
            {"id": "handoff_242489", "question": "242.489 秒发生怎样的前景交接，基底是否仍在？", "ground_truth": "吉他衔接到前景，古筝退出；低音提琴类、电子琴、架子鼓基底继续。"},
            {"id": "melody_unknown", "question": "材料是否支持确定整首歌的旋律轮廓、调性和拍号？", "ground_truth": "不支持；三者均明确为未知或缺少可靠转录。"},
        ],
        "open": [
            {"id": "bridge_observation", "question": "描述 190.860–210.250 秒的音乐组织：先写可核对事实，再写一个自由联想。不要把联想包装成事实。"},
            {"id": "whole_song_motion", "question": "只依据材料中的曲线与事件，概括一次全曲的音乐运动；可以自由选择比喻，但必须把观测和联想分开。"},
        ],
    }


def main() -> None:
    timeline = read_json(SONG / "timeline.reference.json")
    shared = lyric_context(timeline)
    natural = (SONG / "experiments" / "mss-curve-poc" / "outputs" / "natural_hybrid_800.txt").read_text(encoding="utf-8").strip()
    mss = (SONG / "experiments" / "mss-curve-poc" / "outputs" / "mss_curve_800.txt").read_text(encoding="utf-8").strip()
    prompt = questions()["instructions"]
    packets = {
        "a_lyrics_only": f"{prompt}\n\n{shared}",
        "b_natural_layers": f"{prompt}\n\n{shared}\n\n附加音乐材料（客观自然语言＋曲线）：\n{natural}",
        "c_mss_layers": f"{prompt}\n\n{shared}\n\n附加音乐材料（分层 MSS＋曲线）：\n{mss}",
    }
    write_text(OUT / "shared-lyrics.txt", shared)
    for name, packet in packets.items():
        write_text(OUT / "conditions" / f"{name}.txt", packet)
    write_json(OUT / "questions.json", questions())
    blind = questions()
    blind_lines = [blind["instructions"], "", "客观题"]
    blind_lines.extend(f"{index}. [{item['id']}] {item['question']}" for index, item in enumerate(blind["objective"], 1))
    blind_lines.extend(["", "开放题"])
    blind_lines.extend(f"{index}. [{item['id']}] {item['question']}" for index, item in enumerate(blind["open"], 1))
    write_text(OUT / "questions.blind.md", "\n".join(blind_lines))
    write_json(
        OUT / "metrics.json",
        {
            "notice": "Token ranges are UTF-8 byte proxies, not provider tokenizer counts.",
            "shared_lyrics": size(shared),
            "music_payloads": {
                "a_lyrics_only": size(""),
                "b_natural_layers": size(natural),
                "c_mss_layers": size(mss),
            },
            "complete_packets": {name: size(packet) for name, packet in packets.items()},
            "paid_model_calls": 0,
        },
    )
    print("Built layered MSS blind-test packets")
    for name, payload in (("b_natural_layers", natural), ("c_mss_layers", mss)):
        measured = size(payload)
        print(f"{name}: {measured['utf8_bytes']} bytes, proxy {measured['estimated_tokens_low']}-{measured['estimated_tokens_high']}")


if __name__ == "__main__":
    main()
