"""Read and write the list of already processed YouTube video IDs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_VIDEOS_PATH = PROJECT_ROOT / "data" / "processed_videos.json"


def load_processed_video_ids() -> set[str]:
    """Load processed YouTube video IDs from the state file.

    If the file is missing or broken, return an empty set instead of stopping
    the whole program. This lets a beginner recover by fixing the file later.
    """

    if not PROCESSED_VIDEOS_PATH.exists():
        return set()

    try:
        raw_data = json.loads(PROCESSED_VIDEOS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    video_ids = _extract_video_ids(raw_data)
    return set(video_ids)


def save_processed_video_ids(video_ids: set[str]) -> None:
    """Save processed YouTube video IDs to the state file."""

    PROCESSED_VIDEOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "processed_video_ids": sorted(video_ids),
    }
    PROCESSED_VIDEOS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_processed(video_id: str) -> bool:
    """Return True if the given YouTube video ID was already processed."""

    return video_id in load_processed_video_ids()


def mark_processed(video_id: str) -> None:
    """Record a YouTube video ID as processed."""

    video_ids = load_processed_video_ids()
    video_ids.add(video_id)
    save_processed_video_ids(video_ids)


def _extract_video_ids(raw_data: Any) -> list[str]:
    """Safely extract video IDs from the JSON payload."""

    if not isinstance(raw_data, dict):
        return []

    raw_video_ids = raw_data.get("processed_video_ids", [])
    if not isinstance(raw_video_ids, list):
        return []

    return [video_id for video_id in raw_video_ids if isinstance(video_id, str)]

