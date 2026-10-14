#!/usr/bin/env python3
"""Build the small, public page payload from the canonical song data."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SONG_DIR = ROOT / "data" / "songs" / "jieyue"
OUTPUT = ROOT / "web" / "music" / "data" / "song.json"

CREDIT_ROWS = (
    ("作词", "lyrics"),
    ("作曲", "composition"),
    ("编曲", "arrangement"),
    ("混音", "mixing"),
    ("修音", "vocal_tuning"),
    ("母带", "mastering"),
    ("MV 制作", "mv_production"),
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    metadata = read_json(SONG_DIR / "metadata.json")
    timeline = read_json(SONG_DIR / "timeline.reference.json")
    video_url = os.environ.get(
        "JIEYUE_VIDEO_URL", "./media/jieyue-mv-720p.mp4"
    )

    public_sections = [
        {
            "id": section["id"],
            "title": section["title"],
            "start_ms": section["start_ms"],
            "end_ms": section["end_ms"],
        }
        for section in timeline["sections"]
        if "video" in section["media"]
    ]

    payload = {
        "schema_version": "0.1.0",
        "song": {
            "id": metadata["song_id"],
            "title": metadata["title"],
            "version_id": metadata["version"]["id"],
            "version_name": metadata["version"]["display_name"],
            "duration_ms": metadata["duration_ms"],
        },
        "media": {
            "video_url": video_url,
            "poster_url": "./assets/poster.jpg",
            "video_duration_ms": metadata["media"]["video"]["duration_ms"],
            "width": metadata["media"]["video"]["width"],
            "height": metadata["media"]["video"]["height"],
            "fps": metadata["media"]["video"]["fps"],
        },
        "credits": [
            {"label": label, "names": metadata["credits"][key]}
            for label, key in CREDIT_ROWS
        ],
        "performers": timeline["performers"],
        "sections": public_sections,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} with "
        f"{len(payload['performers'])} performers and "
        f"{len(payload['sections'])} sections."
    )


if __name__ == "__main__":
    main()
