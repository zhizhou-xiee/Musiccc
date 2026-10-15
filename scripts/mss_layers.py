"""Derive explicit foreground/background texture layers from MSS events.

The source annotations remain the human listening record.  These fields only
make temporal overlap explicit so a compact representation does not imply that
a foreground accent replaced the accompaniment underneath it.
"""

from __future__ import annotations

from typing import Any


BACKGROUND_TYPES = {"texture_state", "texture_expansion"}
FOREGROUND_TYPES = {
    "instrument_accent",
    "instrument_accent_and_entry",
    "instrument_accent_window",
    "foreground_change",
    "foreground_handoff",
    "instrument_entry",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _covering_backgrounds(event: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in events
        if candidate["id"] != event["id"]
        and candidate["section_id"] == event["section_id"]
        and candidate["type"] in BACKGROUND_TYPES
        and candidate.get("end_ms") is not None
        and candidate["start_ms"] <= event["start_ms"] <= candidate["end_ms"]
    ]


def _foreground_instruments(event: dict[str, Any]) -> list[str]:
    if event.get("foreground"):
        return [event["foreground"]]
    if event["id"] == "detail-event-008":
        return ["guzheng"]
    if event["type"] in {
        "instrument_accent",
        "instrument_accent_window",
    }:
        return list(event.get("instruments", []))
    if event.get("instrument_candidates") and event["type"] in FOREGROUND_TYPES:
        return []
    return []


def _layer_role(event: dict[str, Any], foreground: list[str]) -> str:
    if event["type"] in BACKGROUND_TYPES:
        return "background_texture"
    if event["type"] == "texture_exit":
        return "background_exit"
    if event["type"] == "texture_reduction":
        return "foreground_solo_after_reduction"
    if event["type"] in {"instrument_accent", "instrument_accent_window"}:
        return "foreground_accent"
    if foreground or event.get("instrument_candidates"):
        return "foreground_over_background"
    return "texture_event"


def enrich_events(source_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy events and attach a derived ``texture_layer`` object."""
    enriched: list[dict[str, Any]] = []
    for source_event in source_events:
        event = dict(source_event)
        foreground = _foreground_instruments(event)
        foreground_candidates = (
            list(event.get("instrument_candidates", []))
            if event["type"] in FOREGROUND_TYPES
            else []
        )
        backgrounds = _covering_backgrounds(event, source_events)

        # At 119.138 s the flute exits and the plucked-string foreground takes
        # over.  The listening note only removes the flute, so the other four
        # instruments from event 014 continue as the accompaniment until the
        # explicit reduction at 127.558 s.
        continuity = "derived_from_overlapping_human_intervals"
        if event["id"] == "detail-event-015":
            backgrounds = [item for item in source_events if item["id"] == "detail-event-014"]
            continuity = "derived_from_human_handoff_without_background_exit"

        background_instruments = _unique(
            [
                instrument
                for background in backgrounds
                for instrument in background.get("instruments", [])
                if instrument not in foreground
            ]
        )
        if event["id"] == "detail-event-015":
            background_instruments = [item for item in background_instruments if item != "dizi"]

        # Some foreground events carry their own embedded accompaniment rather
        # than pointing to a separate background event.
        background_instruments = _unique(
            background_instruments
            + [
                instrument
                for instrument in event.get("instruments", [])
                if instrument not in foreground
                and instrument != event.get("foreground")
                and event["type"] in {"instrument_entry", "foreground_change", "foreground_handoff"}
            ]
        )

        background_additions: list[str] = []
        if event["id"] == "detail-event-008":
            background_additions = ["shaker_family", "drum_kit"]
            background_instruments = _unique(background_instruments + background_additions)

        if event["type"] in BACKGROUND_TYPES:
            foreground = []
            foreground_candidates = []
            background_instruments = list(event.get("instruments", []))
            backgrounds = []
            continuity = "direct_human_annotation"
        elif event["type"] in {"texture_exit", "texture_reduction"}:
            background_instruments = []
            backgrounds = []
            continuity = "direct_human_transition"

        event["texture_layer"] = {
            "role": _layer_role(event, foreground),
            "foreground_instruments": foreground,
            "foreground_candidates": foreground_candidates,
            "background_instruments": background_instruments,
            "background_event_ids": [item["id"] for item in backgrounds],
            "background_additions": background_additions,
            "continuity": continuity,
            "status": "derived_from_human_listening_events",
        }
        enriched.append(event)
    return enriched

