"""Fetch transcript text for a YouTube video."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)

PREFERRED_TRANSCRIPT_LANGUAGES = ("ko", "en")


def get_transcript_text(video_id: str) -> str | None:
    """Return transcript text for a YouTube video, or None if unavailable.

    Korean captions are preferred. If Korean captions are not available, English
    captions are used. This function intentionally returns None on failure so
    the whole program can continue running when one video has no transcript.
    """

    if not video_id.strip():
        logger.warning(
            "자막을 가져오지 못했습니다: video_id가 비어 있습니다. "
            "초보자 안내: YouTube 영상 URL 전체가 아니라 영상 ID만 전달해야 합니다."
        )
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.warning(
            "자막 패키지 youtube-transcript-api를 찾을 수 없습니다. "
            "초보자 안내: 가상환경을 켠 뒤 `pip install -e .` 명령어로 "
            "프로젝트 의존성을 설치하세요."
        )
        return None

    try:
        fetched_transcript = YouTubeTranscriptApi().fetch(
            video_id,
            languages=list(PREFERRED_TRANSCRIPT_LANGUAGES),
        )
    except Exception as exc:
        logger.warning(
            "YouTube 자막을 가져오지 못했습니다. video_id=%s, 이유=%s. "
            "초보자 안내: 이 영상에 한국어/영어 자막이 없거나, "
            "영상이 비공개/연령 제한 상태이거나, YouTube가 일시적으로 "
            "자막 접근을 막았을 수 있습니다.",
            video_id,
            exc,
        )
        return None

    transcript_text = _join_transcript_text(fetched_transcript)
    if not transcript_text:
        logger.warning(
            "YouTube 자막을 가져왔지만 내용이 비어 있습니다. video_id=%s. "
            "초보자 안내: 이 영상의 자막 데이터가 비어 있을 수 있습니다.",
            video_id,
        )
        return None

    return transcript_text


def _join_transcript_text(fetched_transcript: Any) -> str:
    """Join transcript snippets into one plain text string."""

    snippets: list[str] = []

    for snippet in fetched_transcript:
        text = _get_snippet_text(snippet)
        if text:
            snippets.append(text.strip())

    return "\n".join(snippets).strip()


def _get_snippet_text(snippet: Any) -> str:
    """Read transcript snippet text from object-style or dict-style data."""

    if isinstance(snippet, dict):
        text = snippet.get("text", "")
    else:
        text = getattr(snippet, "text", "")

    return text if isinstance(text, str) else ""

