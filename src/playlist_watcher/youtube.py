"""Fetch recent videos from a YouTube playlist."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from playlist_watcher.config import AppConfig, load_config


YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch"
YOUTUBE_MAX_RESULTS_LIMIT = 50


class YouTubeAPIError(RuntimeError):
    """Raised when YouTube playlist videos cannot be fetched."""


def get_latest_playlist_videos(
    config: AppConfig | None = None,
) -> list[dict[str, str]]:
    """Return recent videos from the configured YouTube playlist.

    Returned item shape:
    {
        "video_id": "",
        "title": "",
        "description": "",
        "published_at": "",
        "url": ""
    }

    This function only fetches basic playlist video metadata. It does not
    collect transcripts, analyze content, send email, or update processed state.
    """

    app_config = config or load_config()
    max_results = min(app_config.max_videos_to_check, YOUTUBE_MAX_RESULTS_LIMIT)
    response_data = _request_playlist_items(app_config, max_results)
    videos = [_playlist_item_to_video(item) for item in response_data.get("items", [])]
    return [video for video in videos if video is not None][
        : app_config.max_videos_to_check
    ]


def _request_playlist_items(
    config: AppConfig,
    max_results: int,
) -> dict[str, Any]:
    """Request playlist items from the YouTube Data API."""

    query = urlencode(
        {
            "part": "snippet",
            "playlistId": config.playlist_id,
            "maxResults": str(max_results),
            "key": config.youtube_api_key,
        }
    )
    request_url = f"{YOUTUBE_PLAYLIST_ITEMS_URL}?{query}"

    try:
        with urlopen(request_url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = _read_error_message(exc)
        raise YouTubeAPIError(
            "YouTube 영상 목록을 가져오지 못했습니다.\n"
            f"HTTP 상태 코드: {exc.code}\n"
            f"상세 내용: {message}\n"
            "초보자 안내: YOUTUBE_API_KEY가 맞는지, PLAYLIST_ID가 맞는지, "
            "Google Cloud에서 YouTube Data API v3가 사용 설정되어 있는지 확인하세요."
        ) from exc
    except URLError as exc:
        raise YouTubeAPIError(
            "YouTube API에 연결하지 못했습니다.\n"
            f"상세 내용: {exc.reason}\n"
            "초보자 안내: 인터넷 연결 상태를 확인한 뒤 다시 실행해보세요."
        ) from exc
    except json.JSONDecodeError as exc:
        raise YouTubeAPIError(
            "YouTube API 응답을 읽지 못했습니다.\n"
            "초보자 안내: 잠시 후 다시 실행해보고, 같은 문제가 반복되면 "
            "API 응답 형식이 바뀌었는지 확인해야 합니다."
        ) from exc


def _playlist_item_to_video(item: Any) -> dict[str, str] | None:
    """Convert one YouTube playlist item into the project video shape."""

    if not isinstance(item, dict):
        return None

    snippet = item.get("snippet", {})
    if not isinstance(snippet, dict):
        return None

    resource_id = snippet.get("resourceId", {})
    if not isinstance(resource_id, dict):
        return None

    video_id = resource_id.get("videoId")
    if not isinstance(video_id, str) or not video_id:
        return None

    return {
        "video_id": video_id,
        "title": _string_or_empty(snippet.get("title")),
        "description": _string_or_empty(snippet.get("description")),
        "published_at": _string_or_empty(snippet.get("publishedAt")),
        "url": f"{YOUTUBE_WATCH_URL}?v={video_id}",
    }


def _read_error_message(exc: HTTPError) -> str:
    """Read a helpful error message from an HTTPError."""

    try:
        raw_body = exc.read().decode("utf-8")
    except OSError:
        return "응답 내용을 읽을 수 없습니다."

    if not raw_body:
        return "응답 내용이 비어 있습니다."

    try:
        parsed_body = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body

    error = parsed_body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message

    return raw_body


def _string_or_empty(value: Any) -> str:
    """Return a string value or an empty string."""

    return value if isinstance(value, str) else ""

