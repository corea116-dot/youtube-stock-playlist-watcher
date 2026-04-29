"""Fetch recent videos from a YouTube playlist."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from playlist_watcher.config import AppConfig, load_config


logger = logging.getLogger(__name__)

YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch"
YOUTUBE_MAX_RESULTS_LIMIT = 50


class YouTubeAPIError(RuntimeError):
    """Raised when YouTube playlist videos cannot be fetched."""


def get_latest_playlist_videos(
    config: AppConfig | None = None,
) -> list[dict[str, Any]]:
    """Return recent videos from the configured YouTube playlist.

    Returned item shape:
    {
        "playlist_id": "",
        "video_id": "",
        "title": "",
        "description": "",
        "channel_title": "",
        "published_at": "",
        "tags": [],
        "url": ""
    }

    This function only fetches basic playlist video metadata. It does not
    collect transcripts, analyze content, send email, or update processed state.
    """

    app_config = config or load_config()
    max_results = min(app_config.max_videos_to_check, YOUTUBE_MAX_RESULTS_LIMIT)
    videos: list[dict[str, Any]] = []

    for playlist_id in app_config.playlist_ids:
        try:
            response_data = _request_playlist_items(app_config, playlist_id, max_results)
        except YouTubeAPIError as exc:
            logger.warning(
                "재생목록 조회에 실패했지만 다른 재생목록 처리는 계속합니다. "
                "playlist_id=%s, 이유=%s",
                playlist_id,
                exc,
            )
            continue

        playlist_videos = [
            _playlist_item_to_video(item, playlist_id)
            for item in response_data.get("items", [])
        ]
        valid_playlist_videos = [video for video in playlist_videos if video is not None]
        limited_videos = valid_playlist_videos[: app_config.max_videos_to_check]
        videos.extend(_enrich_videos_with_snippets(app_config, limited_videos))

    return videos


def get_video_comments(video_id: str, max_results: int = 20) -> list[str]:
    """Return top-level YouTube comments for a video, or an empty list on failure."""

    if not video_id.strip():
        return []

    config = load_config()
    safe_max_results = max(1, min(max_results, 100))
    query = urlencode(
        {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": str(safe_max_results),
            "order": "relevance",
            "textFormat": "plainText",
            "key": config.youtube_api_key,
        }
    )

    try:
        response_data = _request_json(f"{YOUTUBE_COMMENT_THREADS_URL}?{query}")
    except YouTubeAPIError as exc:
        logger.warning(
            "댓글을 가져오지 못했습니다. video_id=%s, 이유=%s. "
            "초보자 안내: 댓글이 비활성화되었거나 API 제한이 있을 수 있습니다.",
            video_id,
            exc,
        )
        return []

    comments: list[str] = []
    for item in response_data.get("items", []):
        comment_text = _extract_top_level_comment_text(item)
        if comment_text:
            comments.append(comment_text)

    return comments


def _request_playlist_items(
    config: AppConfig,
    playlist_id: str,
    max_results: int,
) -> dict[str, Any]:
    """Request playlist items from the YouTube Data API."""

    query = urlencode(
        {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": str(max_results),
            "key": config.youtube_api_key,
        }
    )
    request_url = f"{YOUTUBE_PLAYLIST_ITEMS_URL}?{query}"

    return _request_json(request_url)


def _request_json(request_url: str) -> dict[str, Any]:
    """Request JSON from YouTube Data API."""

    try:
        with urlopen(request_url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = _read_error_message(exc)
        raise YouTubeAPIError(
            "YouTube API 요청에 실패했습니다.\n"
            f"HTTP 상태 코드: {exc.code}\n"
            f"상세 내용: {message}\n"
            "초보자 안내: YOUTUBE_API_KEY가 맞는지, PLAYLIST_IDS 또는 PLAYLIST_ID가 맞는지, "
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


def _playlist_item_to_video(item: Any, playlist_id: str) -> dict[str, Any] | None:
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
        "playlist_id": playlist_id,
        "video_id": video_id,
        "title": _string_or_empty(snippet.get("title")),
        "description": _string_or_empty(snippet.get("description")),
        "channel_title": _string_or_empty(snippet.get("channelTitle")),
        "published_at": _string_or_empty(snippet.get("publishedAt")),
        "tags": [],
        "url": f"{YOUTUBE_WATCH_URL}?v={video_id}",
    }


def _enrich_videos_with_snippets(
    config: AppConfig,
    videos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add videos.list snippet fields such as tags and channel title when possible."""

    video_ids = [video["video_id"] for video in videos if video.get("video_id")]
    if not video_ids:
        return videos

    query = urlencode(
        {
            "part": "snippet",
            "id": ",".join(video_ids),
            "key": config.youtube_api_key,
        }
    )

    try:
        response_data = _request_json(f"{YOUTUBE_VIDEOS_URL}?{query}")
    except YouTubeAPIError as exc:
        logger.warning(
            "영상 메타데이터 보강에 실패했지만 기본 정보로 계속 진행합니다. 이유=%s",
            exc,
        )
        return videos

    snippets_by_video_id = {
        item.get("id"): item.get("snippet", {})
        for item in response_data.get("items", [])
        if isinstance(item, dict)
    }

    for video in videos:
        snippet = snippets_by_video_id.get(video.get("video_id"))
        if not isinstance(snippet, dict):
            continue
        video["title"] = _string_or_empty(snippet.get("title")) or video.get("title", "")
        video["description"] = _string_or_empty(snippet.get("description")) or video.get("description", "")
        video["channel_title"] = _string_or_empty(snippet.get("channelTitle")) or video.get("channel_title", "")
        video["published_at"] = _string_or_empty(snippet.get("publishedAt")) or video.get("published_at", "")
        raw_tags = snippet.get("tags", [])
        video["tags"] = raw_tags if isinstance(raw_tags, list) else []

    return videos


def _extract_top_level_comment_text(item: Any) -> str:
    """Extract top-level comment text from a commentThread item."""

    if not isinstance(item, dict):
        return ""
    snippet = item.get("snippet", {})
    if not isinstance(snippet, dict):
        return ""
    top_level_comment = snippet.get("topLevelComment", {})
    if not isinstance(top_level_comment, dict):
        return ""
    comment_snippet = top_level_comment.get("snippet", {})
    if not isinstance(comment_snippet, dict):
        return ""
    return _string_or_empty(comment_snippet.get("textOriginal")) or _string_or_empty(
        comment_snippet.get("textDisplay")
    )


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
