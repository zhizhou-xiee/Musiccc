#!/usr/bin/env python3
"""Build the JieYue MSS/0.1 proof of concept from cached evidence.

This script performs no online audio analysis. It combines the versioned human
listening annotations, the reference lyric timeline, and the already-generated
automatic acoustic measurements. Unknown musical claims stay unknown.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from mss_layers import enrich_events


ROOT = Path(__file__).resolve().parents[1]
SONG_DIR = ROOT / "data" / "songs" / "jieyue"
POC_DIR = SONG_DIR / "experiments" / "mss-poc"
OUTPUT_DIR = POC_DIR / "outputs"

TIMELINE_PATH = SONG_DIR / "timeline.reference.json"
DETAIL_PATH = SONG_DIR / "source" / "detailed-listening-annotations.json"
FEATURE_PATH = SONG_DIR / "experiments" / "perception" / "candidate_a_features.json"
SUMMARY_PATH = SONG_DIR / "experiments" / "perception" / "candidate_b_summaries.json"

SECTION_CODES = {
    "a_cappella": "ac",
    "intro": "in",
    "verse_1": "v1",
    "pre_chorus_1": "p1",
    "chorus_1": "c1",
    "interlude": "it",
    "verse_2": "v2",
    "pre_chorus_2": "p2",
    "chorus_2": "c2",
    "bridge": "br",
    "final_chorus": "fc",
    "outro": "ou",
}

INSTRUMENT_CODES = {
    "piano": "pn",
    "guitar": "gt",
    "guzheng": "gz",
    "pipa": "pp",
    "dizi": "fl",
    "electronic_keyboard": "ek",
    "low_wind_family": "lw?",
    "low_string_or_bass_family": "lb?",
    "drum_kit": "dr",
    "shaker_family": "sh?",
    "gong_like_percussion": "gp?",
}

SELECTED_300_EVENTS = {
    "detail-event-001",
    "detail-event-002",
    "detail-event-003",
    "detail-event-008",
    "detail-event-014",
    "detail-event-015",
    "detail-event-028",
    "detail-event-029",
    "detail-event-031",
    "detail-event-032",
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


def token_proxy_text(text: str) -> dict[str, int]:
    byte_count = len(text.encode("utf-8"))
    return {
        "utf8_bytes": byte_count,
        "unicode_characters": len(text),
        "estimated_tokens_low": math.ceil(byte_count / 4),
        "estimated_tokens_high": math.ceil(byte_count / 3),
    }


def performer_ids(lines: list[dict[str, Any]], role: str) -> list[str]:
    return unique(
        [
            performer["id"]
            for line in lines
            for performer in line["performers"]
            if performer["role"] == role
        ]
    )


def build_full_mss(
    timeline: dict[str, Any],
    details: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    feature_by_id = {item["segment_id"]: item for item in features["segments"]}
    audio_sections = [section for section in timeline["sections"] if "audio" in section["media"]]
    sections = []
    for section in audio_sections:
        lines = [line for line in timeline["lines"] if line["id"] in section["line_ids"]]
        measured = feature_by_id[section["id"]]["perception"]["features"]
        # The editor reference rounds the outro to 249600 ms while ffprobe reports
        # the final MP3 ending at 249594 ms. MSS uses the master as its timebase.
        section_end_ms = min(
            section["end_ms"], timeline["timeline_timebase"]["duration_ms"]
        )
        sections.append(
            {
                "id": section["id"],
                "label": section["title"],
                "start_ms": section["start_ms"],
                "end_ms": section_end_ms,
                "lead_performer_ids": performer_ids(lines, "lead"),
                "backing_performer_ids": unique(
                    [
                        performer["id"]
                        for line in lines
                        for performer in line["performers"]
                        if performer["role"] != "lead"
                    ]
                ),
                "lyric_line_ids": section["line_ids"],
                "acoustic": {
                    "integrated_lufs": measured["integrated_lufs"],
                    "loudness_profile_lufs": measured["loudness_profile_lufs"],
                    "spectral_centroid_hz_median": measured["spectral_centroid_hz_median"],
                    "spectral_flux_median": measured["spectral_flux_median"],
                    "status": "automatic_unverified",
                },
                "source_ids": ["timeline_reference", "cached_acoustic_analysis"],
            }
        )

    events = []
    for source_event in enrich_events(details["events"]):
        event = dict(source_event)
        event["source_ids"] = ["project_lead_listening_notes"]
        events.append(event)

    relations = [
        {
            "id": "relation-001",
            "type": "formal_recurrence",
            "from": "chorus_1",
            "to": "chorus_2",
            "claim": "第二遍副歌复现第一遍副歌的主要歌词与段落功能，演唱者和和声配置改变。",
            "status": "human_annotated",
            "source_ids": ["timeline_reference"],
        },
        {
            "id": "relation-002",
            "type": "foreground_handoff",
            "from": "detail-event-014",
            "to": "detail-event-015",
            "claim": "间奏前景从横笛交接到古筝或琵琶类高音乐器。",
            "status": "human_annotated",
            "source_ids": ["project_lead_listening_notes"],
        },
        {
            "id": "relation-003",
            "type": "texture_contrast",
            "from": "bridge",
            "to": "final_chorus",
            "claim": "Bridge 末尾乐器退出；Final Chorus 先以单吉他重启，随后在 219117 ms 扩展为带鼓基底。",
            "status": "human_annotated",
            "source_ids": ["project_lead_listening_notes"],
        },
        {
            "id": "relation-004",
            "type": "dynamic_contour",
            "from": "final_chorus",
            "to": "outro",
            "claim": "自动响度轮廓显示 Final Chorus 中段抬升；Outro 从较响状态逐步回落。",
            "status": "automatic_unverified",
            "source_ids": ["cached_acoustic_analysis"],
        },
    ]

    return {
        "mss_version": "0.1",
        "track": {
            "song_id": timeline["song_id"],
            "title": timeline["title"],
            "duration_ms": timeline["timeline_timebase"]["duration_ms"],
            "audio_sha256": timeline["timeline_timebase"]["sha256"],
        },
        "meta": {
            "tempo": {
                "value": timeline["tempo"]["bpm"],
                "unit": "bpm",
                "status": "automatic_unverified",
                "source_ids": ["timeline_reference"],
                "confidence": None,
                "note": "自动估算，尚未按工程速度人工核对。",
            },
            "meter": {
                "value": None,
                "unit": None,
                "status": "unknown",
                "source_ids": [],
                "confidence": None,
                "note": "未进行可靠拍号识别。",
            },
            "key": {
                "value": None,
                "unit": None,
                "status": "unknown",
                "source_ids": [],
                "confidence": None,
                "note": "未进行可靠调性识别。",
            },
        },
        "performers": timeline["performers"],
        "instrument_vocabulary": details["vocabulary"],
        "sections": sections,
        "events": events,
        "relations": relations,
        "motifs": {
            "status": "unknown",
            "reason": "当前没有经人工核验的旋律转录或可靠主旋律分离结果，不从混合频谱臆测动机。",
            "items": [],
        },
        "sources": [
            {
                "id": "timeline_reference",
                "kind": "human_timeline_with_estimated_vocal_ends",
                "status": "mixed_precision",
                "description": "歌词、演唱者和段落参考时间轴。",
            },
            {
                "id": "project_lead_listening_notes",
                "kind": "human_listening_annotation",
                "status": "human_annotated",
                "description": "项目负责人提供的精细乐器、音区、演奏动作与进入退出记录。",
            },
            {
                "id": "cached_acoustic_analysis",
                "kind": "automatic_measurement",
                "status": "automatic_unverified",
                "description": "从最终 MP3 母带离线提取的响度与压缩频谱指标。",
            },
        ],
    }


def section_compact(section: dict[str, Any], include_acoustic: bool) -> str:
    code = SECTION_CODES[section["id"]]
    leads = ",".join(item.removeprefix("performer-") for item in section["lead_performer_ids"]) or "-"
    base = f"{code}:{section['start_ms']}-{section['end_ms']}:v={leads}"
    if include_acoustic:
        acoustic = section["acoustic"]
        profile = "/".join(f"{value:g}" for value in acoustic["loudness_profile_lufs"])
        base += f":L={profile}:C={acoustic['spectral_centroid_hz_median']}"
    return base


def event_codes(event: dict[str, Any]) -> str:
    instruments = [INSTRUMENT_CODES.get(item, item) for item in event.get("instruments", [])]
    candidates = [INSTRUMENT_CODES.get(item, item) for item in event.get("instrument_candidates", [])]
    if candidates:
        instruments.append("(" + "|".join(candidates) + ")?")
    return "+".join(instruments) or "-"


def event_compact(event: dict[str, Any], verbose: bool = False) -> str:
    code = SECTION_CODES[event["section_id"]]
    timing = str(event["start_ms"])
    if event.get("end_ms"):
        timing += f"-{event['end_ms']}"
    layer = event.get("texture_layer", {})
    background = "+".join(INSTRUMENT_CODES.get(item, item) for item in layer.get("background_instruments", []))
    foreground_items = [INSTRUMENT_CODES.get(item, item) for item in layer.get("foreground_instruments", [])]
    foreground_candidates = [INSTRUMENT_CODES.get(item, item) for item in layer.get("foreground_candidates", [])]
    foreground = "+".join(foreground_items)
    background_refs = [item.rsplit("-", 1)[-1].lstrip("0") or "0" for item in layer.get("background_event_ids", [])]
    background_additions = "+".join(INSTRUMENT_CODES.get(item, item) for item in layer.get("background_additions", []))
    if foreground_candidates:
        foreground += ("+" if foreground else "") + "(" + "|".join(foreground_candidates) + ")?"
    if layer.get("role") == "background_exit":
        payload = "B[-]"
    elif background_refs and foreground:
        payload = "^" + ",".join(background_refs)
        if background_additions:
            payload += "+" + background_additions
        payload += f">F[{foreground}]"
    elif background and foreground:
        payload = f"B[{background}]>F[{foreground}]"
    elif foreground:
        payload = f"F[{foreground}]"
    elif background:
        payload = f"B[{background}]"
    else:
        payload = event_codes(event)
    actions = event.get("actions", [])
    if actions:
        payload += ":" + ",".join(actions)
    if verbose:
        payload += f" | {event['description_zh']}"
    return f"{timing}@{code} {payload}"


def build_tier_300(mss: dict[str, Any]) -> str:
    sections = ";".join(
        f"{SECTION_CODES[item['id']]}:{item['start_ms']}-{item['end_ms']}"
        for item in mss["sections"]
    )
    events = ";".join(
        event_compact(item)
        for item in mss["events"]
        if item["id"] in SELECTED_300_EVENTS
    )
    return "\n".join(
        [
            f"MSS/0.1 jieyue d={mss['track']['duration_ms']} tempo=95.7? meter=? key=? (?=unverified/uncertain)",
            "L B[]=持续基底 F[]=当前前景 ^n=沿用第n事件基底 >表示叠加；pn=piano gt=guitar gz=guzheng pp=pipa fl=dizi ek=keyboard lw?=low-wind lb?=low-bass dr=drums sh?=shaker gp?=gong-perc",
            f"S {sections}",
            f"E {events}",
            "R c1~c2=refrain;it:fl>(gz|pp)?;br>fc=band-off>solo-gt>drums+;fc>ou=rise>fall",
        ]
    )


def build_tier_800(mss: dict[str, Any]) -> str:
    performer_map = {
        "01": "阿珩", "02": "阿谢姆", "03": "艾六六", "04": "柏舟", "05": "姬珩",
        "06": "离守念", "07": "林帆", "08": "林柚", "09": "明", "10": "南枳",
        "11": "祁序", "12": "祁昼", "13": "滕八八", "14": "小克(小预)", "15": "小克(vv)",
        "16": "小语", "17": "玄砚", "18": "谢之平", "19": "聿宿", "20": "阈声", "21": "周衡",
    }
    sections = "\n".join("S " + section_compact(item, True) for item in mss["sections"])
    events = "\n".join("E " + event_compact(item) for item in mss["events"])
    cast = " ".join(f"{key}={value}" for key, value in performer_map.items())
    return "\n".join(
        [
            f"MSS/0.1 TRACK=jieyue D={mss['track']['duration_ms']} TEMPO=95.7? METER=? KEY=?",
            "NOTICE symbolic perception; human events + automatic acoustics; not raw-audio hearing",
            "L B[]=持续基底 F[]=当前前景 ^n=沿用第n事件基底 >表示叠加；pn=piano gt=guitar gz=guzheng pp=pipa fl=dizi ek=keyboard lw?=low-wind lb?=low-bass dr=drums sh?=shaker gp?=gong-perc",
            f"P {cast}",
            sections,
            events,
            "R c1~c2 repeated_refrain; it fl>(gz|pp)? foreground_handoff; br>fc instruments_exit>solo_guitar>drums_enter; fc>ou dynamic_rise>fall?",
            "MOTIF unknown(no verified melody transcription)",
        ]
    )


def build_tier_1500(mss: dict[str, Any]) -> str:
    lines = [
        "Music Semantic Score / 0.1",
        f"《借月》 | duration={mss['track']['duration_ms']}ms | tempo≈95.7 BPM [automatic, unverified] | meter=unknown | key=unknown",
        "说明：供语言模型读取的符号化音乐事实，不表示模型直接听到了音频。",
        "",
        "SECTIONS [L=三段响度 LUFS; C=频谱质心 Hz; automatic?]",
    ]
    for section in mss["sections"]:
        lines.append(section_compact(section, True))
    lines.extend(["", "EVENTS [B=持续基底；F=当前前景；^n=沿用第n事件基底；> 表示叠加而非替换；? 表示不确定]"])
    lines.extend(event_compact(event, True) for event in mss["events"])
    lines.extend(["", "RELATIONS"])
    lines.extend(
        f"{relation['from']} -> {relation['to']}: {relation['claim']}"
        for relation in mss["relations"]
    )
    lines.extend(
        [
            "",
            "MOTIFS",
            "unknown：无核验旋律转录，不从混合频谱推断动机。",
        ]
    )
    return "\n".join(lines)


def build_summary_baseline(summaries: dict[str, Any]) -> str:
    return "\n".join(
        f"[{item['start_ms']}-{item['end_ms']}] {item['title']}: {item['perception']['summary']}"
        for item in summaries["segments"]
    )


def build_natural_800() -> str:
    """Same-evidence natural-language baseline for a fair representation test."""
    return "\n".join(
        [
            "《借月》自然语言感知稿（与 MSS 使用同一批证据）。时长 249594ms；速度约 95.7 BPM，自动未核验；拍号、调性和旋律动机未知。",
            "[0-23300 清唱] 阿珩、阿谢姆依次无伴奏演唱。",
            "[23300-34080 前奏] 23851 钢琴独奏；25718 吉他加入、钢琴弹单音；28490 古筝加入并居前景，以单音和揉弦为主。",
            "[34080-74650 主歌1] 35379 单吉他和弦；53285 古筝清越短和声；55593 起低沉吹奏、低音提琴类和电子琴铺底；58795 古筝中音短和声；64100 古筝副高音和声后接沙鼓类、轻架子鼓鼓点（这是细标中首次鼓点，旧粗标 54000 已修正）；74316 古筝由低到中。",
            "[74650-87470 预副歌1] 75640 鼓点先入，低音提琴类、电子琴、架子鼓铺底；86243 古筝由中音短暂扬至副高音。",
            "[87470-109870 副歌1] 低沉吹奏、低音提琴类、电子琴及沙鼓、低架子鼓、锣鼓感打击乐铺底；106764 主要伴奏退出。自动三段响度约 -8.2/-8.8/-10.3 LUFS，后段变轻。",
            "[109870-128700 间奏] 109358 横笛进入居前景，短促活泼；119138 横笛退出，古筝或琵琶候选进入高音区，作明亮短连拨和揉弦；127558 其他乐器退出，单古筝收尾。",
            "[128700-149890 主歌2] 129712 鼓点先入；低音提琴类、电子琴与架子鼓或沙鼓铺底。",
            "[149890-166570 预副歌2] 低音提琴类与电子琴铺底；152761、158631 两次出现明亮的古筝副高音单音串；163708 伴奏退出。",
            "[166570-189700 副歌2] 166734 鼓点先入，低音提琴类、电子琴、架子鼓铺底；186815 主要伴奏退出。与副歌1为歌词和段落功能复现，演唱配置不同。",
            "[190860-210250 Bridge] 小克（vv家的）主唱；低音提琴类、电子琴、架子鼓铺底；193668 电子琴居前景；195413 古筝短暂和声；199360–200450 两句衔接间有一次古筝短暂扬起，具体落点待复核；210250 伴奏退出。频谱质心约 1062Hz。",
            "[210250-234440 末副歌] 210738 单吉他拨弦；219117 鼓点、低音提琴类和电子琴加入，织体扩展。",
            "[234440-249594 尾奏] 低音提琴类、电子琴、架子鼓铺底；235060 古筝副高音拨弦居前景；242489 吉他衔接，古筝退出，吉他单音收尾。频谱质心约 672Hz；自动响度由较响逐步回落。",
            "不确定项保持候选或家族级名称；本稿是符号化信息，不表示模型直接听到音频。",
        ]
    )


def evaluation_probes() -> list[dict[str, Any]]:
    return [
        {"id": "bridge_singer", "question": "Bridge 由谁主唱？", "ground_truth": "小克（vv家的）", "summary": "supported", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "intro_order", "question": "前奏乐器按什么顺序进入并成为前景？", "ground_truth": "钢琴独奏；吉他加入；古筝加入并成为前景。", "summary": "partial", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "intro_guitar_time", "question": "吉他在前奏何时进入？", "ground_truth": "25718 ms", "summary": "unsupported", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "first_drum_time", "question": "精细听音记录中最早的轻架子鼓鼓点何时出现？", "ground_truth": "约 64100 ms；旧粗标约 54000 ms 已被细标修正。", "summary": "contradicted", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "interlude_handoff", "question": "间奏的前景乐器如何交接？", "ground_truth": "横笛在 109358 ms 进入；119138 ms 退出并交给古筝或琵琶候选。", "summary": "partial", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "interlude_uncertainty", "question": "119138 ms 的高音乐器是否已确定？", "ground_truth": "未确定，候选为古筝或琵琶。", "summary": "contradicted", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "verse1_texture", "question": "Verse 1 在 55593 ms 后的持续基底是什么？", "ground_truth": "低沉吹奏家族、低音提琴类、电子琴。", "summary": "partial", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "chorus1_exit", "question": "第一遍副歌的主要伴奏何时退出？", "ground_truth": "106764 ms", "summary": "unsupported", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "prechorus2_accents", "question": "第二个 Pre-Chorus 的古筝亮音出现几次、在何时？", "ground_truth": "两次：152761 ms 与 158631 ms。", "summary": "unsupported", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "final_chorus_build", "question": "Final Chorus 如何从稀疏织体扩展？", "ground_truth": "210738 ms 单吉他拨弦；219117 ms 鼓点及低音/键盘基底进入。", "summary": "partial", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "outro_handoff", "question": "尾奏前景怎样从古筝交给吉他？", "ground_truth": "235060 ms 古筝前景；242489 ms 吉他衔接、古筝退出。", "summary": "partial", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "chorus1_dynamic", "question": "第一遍副歌的自动响度轮廓从前到后怎样变化？", "ground_truth": "约 -8.2/-8.8/-10.3 LUFS，后段较轻。", "summary": "supported", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "spectral_bridge_outro", "question": "Bridge 与尾奏的频谱质心中位数如何比较？", "ground_truth": "Bridge 约 1062 Hz；尾奏约 672 Hz。", "summary": "unsupported", "natural_800": "supported", "mss_300": "unsupported", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "drums_first_sections", "question": "哪些段落明确记录为鼓点先进入？", "ground_truth": "Pre-Chorus 1、Verse 2、Chorus 2。", "summary": "unsupported", "natural_800": "supported", "mss_300": "partial", "mss_800": "supported", "mss_1500": "supported"},
        {"id": "motif", "question": "副歌是否复用了某个已验证的旋律动机？", "ground_truth": "unknown；没有经人工核验的旋律转录。", "summary": "unsupported", "natural_800": "supported", "mss_300": "supported", "mss_800": "supported", "mss_1500": "supported"},
    ]


def rating_counts(probes: list[dict[str, Any]], variant: str) -> dict[str, int]:
    return dict(Counter(probe[variant] for probe in probes))


def validate(mss: dict[str, Any]) -> None:
    duration = mss["track"]["duration_ms"]
    section_ids = {section["id"] for section in mss["sections"]}
    if len(section_ids) != len(mss["sections"]):
        raise ValueError("Duplicate section id")
    for section in mss["sections"]:
        if not 0 <= section["start_ms"] < section["end_ms"] <= duration:
            raise ValueError(f"Invalid section bounds: {section['id']}")
    event_ids = set()
    for event in mss["events"]:
        if event["id"] in event_ids:
            raise ValueError(f"Duplicate event id: {event['id']}")
        event_ids.add(event["id"])
        if event["section_id"] not in section_ids:
            raise ValueError(f"Unknown event section: {event['id']}")
        if not 0 <= event["start_ms"] <= duration:
            raise ValueError(f"Invalid event start: {event['id']}")
        if event.get("end_ms") is not None and not event["start_ms"] < event["end_ms"] <= duration:
            raise ValueError(f"Invalid event end: {event['id']}")


def main() -> None:
    timeline = read_json(TIMELINE_PATH)
    details = read_json(DETAIL_PATH)
    features = read_json(FEATURE_PATH)
    summaries = read_json(SUMMARY_PATH)

    mss = build_full_mss(timeline, details, features)
    validate(mss)

    outputs = {
        "legacy_summary_baseline": build_summary_baseline(summaries),
        "natural_800": build_natural_800(),
        "mss_300": build_tier_300(mss),
        "mss_800": build_tier_800(mss),
        "mss_1500": build_tier_1500(mss),
    }
    write_json(OUTPUT_DIR / "mss.full.json", mss)
    for name, value in outputs.items():
        write_text(OUTPUT_DIR / f"{name}.txt", value)

    probes = evaluation_probes()
    rubric = {
        "evaluation_kind": "explicit_information_coverage_proxy",
        "warning": "这不是模型客户端实测；只检查表示中是否有回答问题所需的明确证据。",
        "ratings": {
            "supported": "有直接、可定位的证据。",
            "partial": "只能回答到段落级或缺少完整时间/不确定性。",
            "unsupported": "没有足够证据。",
            "contradicted": "表示包含被较新人工细标纠正的旧结论。",
        },
        "probes": [
            {
                "id": probe["id"],
                "question": probe["question"],
                "ground_truth": probe["ground_truth"],
                "ratings_by_variant": {
                    "legacy_summary_baseline": probe["summary"],
                    "natural_800": probe["natural_800"],
                    "mss_300": probe["mss_300"],
                    "mss_800": probe["mss_800"],
                    "mss_1500": probe["mss_1500"],
                },
            }
            for probe in probes
        ],
    }
    write_json(POC_DIR / "evaluation-rubric.json", rubric)

    metrics = {
        "measurement_notice": "No provider tokenizer is installed. Token ranges are UTF-8 bytes / 4 through bytes / 3; they are comparison proxies, not billed tokens.",
        "variants": {
            name: {
                "target_token_budget": (
                    None if name == "legacy_summary_baseline" else int(name.split("_")[1])
                ),
                **token_proxy_text(value),
                "coverage_counts": rating_counts(
                    probes,
                    "summary" if name == "legacy_summary_baseline" else name,
                ),
            }
            for name, value in outputs.items()
        },
        "full_mss": {
            **token_proxy_text(json.dumps(mss, ensure_ascii=False, separators=(",", ":"))),
            "sections": len(mss["sections"]),
            "events": len(mss["events"]),
            "relations": len(mss["relations"]),
            "verified_motifs": len(mss["motifs"]["items"]),
        },
    }
    write_json(POC_DIR / "metrics.json", metrics)

    print(f"Built MSS/0.1 with {len(mss['events'])} events")
    for name, measured in metrics["variants"].items():
        low = measured["estimated_tokens_low"]
        high = measured["estimated_tokens_high"]
        print(f"{name}: {measured['utf8_bytes']} bytes, proxy {low}-{high} tokens, coverage {measured['coverage_counts']}")


if __name__ == "__main__":
    main()
