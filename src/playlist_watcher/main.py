"""Command-line entry point for the YouTube stock playlist watcher."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from playlist_watcher.analyzer import analyze_video
from playlist_watcher.config import AppConfig, load_config
from playlist_watcher.emailer import _build_email_message, _send_message
from playlist_watcher.state import load_processed_video_ids, mark_processed
from playlist_watcher.transcript import get_transcript_text
from playlist_watcher.youtube import get_latest_playlist_videos


logger = logging.getLogger(__name__)

Video = dict[str, Any]
Analysis = dict[str, Any]
KST = ZoneInfo("Asia/Seoul")
VALID_TEST_MODES = {"normal", "today", "latest_one"}


def main() -> int:
    """Run the watcher from the command line."""

    _configure_logging()
    return run()


def run(
    load_config_fn: Callable[[], AppConfig] = load_config,
    fetch_videos_fn: Callable[[AppConfig], list[Video]] = get_latest_playlist_videos,
    load_processed_ids_fn: Callable[[], set[str]] = load_processed_video_ids,
    get_transcript_fn: Callable[[str], str | None] = get_transcript_text,
    analyze_fn: Callable[[Video, str | None, AppConfig], Analysis] = analyze_video,
    send_email_fn: Callable[[list[Analysis], AppConfig], bool] | None = None,
    mark_processed_fn: Callable[[str], None] = mark_processed,
    force_reprocess: bool | None = None,
    test_mode: str | None = None,
    current_time_fn: Callable[[], datetime] | None = None,
) -> int:
    """Run the full watcher workflow.

    Dependency arguments make this function easy to test with mocks, so tests do
    not need real YouTube, Gemini, or SMTP credentials.
    """

    if send_email_fn is None:
        send_email_fn = _send_analysis_email_with_success
    force_reprocess_enabled = (
        _read_force_reprocess_from_env() if force_reprocess is None else force_reprocess
    )
    selected_test_mode = (
        _read_test_mode_from_env() if test_mode is None else _normalize_test_mode(test_mode)
    )
    if force_reprocess_enabled and selected_test_mode == "normal":
        selected_test_mode = "latest_one"
        logger.info(
            "FORCE_REPROCESS=true 값을 감지해 TEST_MODE=latest_one처럼 처리합니다. "
            "초보자 안내: 새 방식에서는 GitHub Actions에서 test_mode를 선택하세요."
        )
    today_kst = _today_kst(current_time_fn)

    try:
        config = load_config_fn()
        logger.info("설정값 로드 완료")
        logger.info("TEST_MODE 값: %s", selected_test_mode)
        logger.info("감시하는 재생목록 개수: %s", len(config.playlist_ids))

        videos = fetch_videos_fn(config)
        playlist_counts = _count_videos_by_playlist(videos)
        for playlist_id in config.playlist_ids:
            logger.info(
                "재생목록별 가져온 영상 개수: playlist_id=%s, count=%s",
                playlist_id,
                playlist_counts.get(playlist_id, 0),
            )
        logger.info(
            "전체 후보 영상 개수: %s",
            len(videos),
        )

        processed_video_ids = load_processed_ids_fn()
        processed_count = _count_processed_candidates(videos, processed_video_ids)
        today_video_count = _count_today_videos(videos, today_kst)
        logger.info("이미 처리된 영상 개수: %s", processed_count)
        logger.info("오늘 영상 개수: %s", today_video_count)

        new_videos = _select_videos_to_process(
            videos,
            processed_video_ids,
            selected_test_mode,
            today_kst,
        )
        logger.info("실제 분석할 영상 개수: %s", len(new_videos))
    except Exception as exc:
        logger.error(
            "초기 실행 준비 중 오류가 발생했습니다. 이유=%s. "
            "초보자 안내: 환경변수와 YouTube API 설정을 확인하세요.",
            exc,
        )
        return 1

    if not new_videos:
        logger.info(
            "이메일을 보내지 않습니다. 이유: 분석할 영상이 없습니다. "
            "수동 테스트가 필요하면 Actions에서 test_mode=today 또는 latest_one으로 실행하세요."
        )
        return 0

    logger.info("분석할 영상 %s개를 처리합니다.", len(new_videos))
    analyses: list[Analysis] = []
    analyzed_video_ids: list[str] = []

    for video in new_videos:
        video_id = video["video_id"]
        logger.info(
            "분석 시작: playlist_id=%s, video_id=%s, 제목=%s",
            video.get("playlist_id", ""),
            video_id,
            video.get("title", ""),
        )

        try:
            transcript_text = get_transcript_fn(video_id)
        except Exception as exc:
            logger.warning(
                "자막 수집 중 오류가 발생했지만 계속 진행합니다. video_id=%s, 이유=%s. "
                "초보자 안내: 자막이 없어도 Gemini YouTube URL 직접 분석을 먼저 시도합니다.",
                video_id,
                exc,
            )
            transcript_text = None

        try:
            analysis = analyze_fn(
                _ensure_video_url(video),
                transcript_text,
                config,
            )
        except Exception as exc:
            logger.warning(
                "영상 분석에 실패해 이 영상은 건너뜁니다. video_id=%s, 이유=%s. "
                "초보자 안내: 다른 새 영상이 있으면 계속 처리합니다.",
                video_id,
                exc,
            )
            continue

        enriched_analysis = _attach_video_metadata(analysis, video, selected_test_mode)
        analyses.append(enriched_analysis)
        analyzed_video_ids.append(video_id)
        logger.info("분석 완료: video_id=%s, 제목=%s", video_id, video.get("title", ""))

    if not analyses:
        logger.info(
            "이메일을 보내지 않습니다. 이유: 분석에 성공한 영상이 없습니다. "
            "처리 완료 기록도 추가하지 않습니다."
        )
        return 0

    logger.info("이메일 발송 시도 여부: true, 분석 결과 개수=%s", len(analyses))
    email_sent = send_email_fn(analyses, config)
    if not email_sent:
        logger.warning("이메일 발송 성공/실패 여부: 실패")
        logger.warning(
            "이메일 발송이 실패했으므로 processed_videos.json에 처리 완료로 기록하지 않습니다."
        )
        return 1
    logger.info("이메일 발송 성공/실패 여부: 성공")

    for video_id in analyzed_video_ids:
        try:
            mark_processed_fn(video_id)
            logger.info("처리 완료로 기록했습니다. video_id=%s", video_id)
        except Exception as exc:
            logger.warning(
                "처리 완료 기록 저장에 실패했습니다. video_id=%s, 이유=%s. "
                "초보자 안내: data/processed_videos.json 파일 권한을 확인하세요.",
                video_id,
                exc,
            )
            return 1

    logger.info("전체 실행이 완료되었습니다. 처리한 새 영상 수=%s", len(analyzed_video_ids))
    return 0


def _send_analysis_email_with_success(
    analyses: list[Analysis],
    config: AppConfig,
) -> bool:
    """Send analysis email and return whether delivery succeeded."""

    if not analyses:
        logger.info("이메일을 보내지 않습니다. 이유: 분석 결과가 없습니다.")
        return False

    try:
        message = _build_email_message(
            analyses=analyses,
            sender=config.smtp_user,
            recipient=config.email_to,
        )
        _send_message(
            message=message,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_pass=config.smtp_pass,
        )
    except Exception as exc:
        logger.warning(
            "이메일 발송에 실패했습니다. 이유=%s. "
            "초보자 안내: SMTP 설정과 Gmail App Password를 확인하세요.",
            exc,
        )
        return False

    logger.info("이메일 발송 성공. 수신자=%s", config.email_to)
    return True


def _read_force_reprocess_from_env() -> bool:
    """Read FORCE_REPROCESS=true/false from environment."""

    return os.environ.get("FORCE_REPROCESS", "false").strip().lower() == "true"


def _read_test_mode_from_env() -> str:
    """Read TEST_MODE from environment, defaulting to normal."""

    return _normalize_test_mode(os.environ.get("TEST_MODE", "normal"))


def _normalize_test_mode(value: str | None) -> str:
    """Return a supported test mode with a beginner-friendly fallback."""

    normalized = (value or "normal").strip().lower()
    if normalized in VALID_TEST_MODES:
        return normalized

    logger.warning(
        "알 수 없는 TEST_MODE 값이라 normal로 처리합니다. TEST_MODE=%s, 사용 가능 값=%s",
        value,
        ", ".join(sorted(VALID_TEST_MODES)),
    )
    return "normal"


def _today_kst(current_time_fn: Callable[[], datetime] | None = None) -> date:
    """Return today's date in Korea Standard Time."""

    now = current_time_fn() if current_time_fn is not None else datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    return now.astimezone(KST).date()


def _count_videos_by_playlist(videos: list[Video]) -> dict[str, int]:
    """Count candidate videos by playlist ID."""

    counts: dict[str, int] = {}
    for video in videos:
        playlist_id = str(video.get("playlist_id", "unknown"))
        counts[playlist_id] = counts.get(playlist_id, 0) + 1
    return counts


def _count_processed_candidates(
    videos: list[Video],
    processed_video_ids: set[str],
) -> int:
    """Count unique candidate videos already present in processed state."""

    return len(
        {
            video["video_id"]
            for video in videos
            if video.get("video_id") in processed_video_ids
        }
    )


def _select_videos_to_process(
    videos: list[Video],
    processed_video_ids: set[str],
    test_mode: str,
    today_kst: date,
) -> list[Video]:
    """Select videos for this run according to normal or manual test mode."""

    if test_mode == "latest_one":
        latest_video = _latest_video(videos)
        if latest_video is not None:
            logger.info(
                "TEST_MODE=latest_one 이므로 최신 영상 1개를 처리 대상으로 강제 선택합니다. "
                "video_id=%s, 제목=%s",
                latest_video.get("video_id", ""),
                latest_video.get("title", ""),
            )
            return [latest_video]
        logger.info("TEST_MODE=latest_one 이지만 후보 영상이 없어 강제 재처리할 수 없습니다.")
        return []

    if test_mode == "today":
        today_videos = _filter_today_unique_videos(videos, today_kst)
        if today_videos:
            logger.info(
                "TEST_MODE=today 이므로 한국시간 오늘 올라온 영상 %s개를 처리 대상으로 선택합니다.",
                len(today_videos),
            )
            return today_videos
        logger.info("TEST_MODE=today 이지만 한국시간 오늘 올라온 영상이 없습니다.")
        return []

    return _filter_new_unique_videos(videos, processed_video_ids)


def _latest_video(videos: list[Video]) -> Video | None:
    """Return the latest candidate video by published_at, falling back to order."""

    videos_with_ids = [video for video in videos if video.get("video_id")]
    if not videos_with_ids:
        return None

    return max(
        videos_with_ids,
        key=lambda video: _published_at_datetime(video) or datetime.min.replace(tzinfo=timezone.utc),
    )


def _count_today_videos(videos: list[Video], today_kst: date) -> int:
    """Count unique videos published today in KST."""

    return len(
        {
            video["video_id"]
            for video in videos
            if video.get("video_id") and _is_published_today(video, today_kst)
        }
    )


def _filter_today_unique_videos(videos: list[Video], today_kst: date) -> list[Video]:
    """Return unique videos published today in KST, even if already processed."""

    seen_video_ids: set[str] = set()
    today_videos: list[Video] = []

    for video in videos:
        video_id = video.get("video_id")
        if not video_id:
            continue
        if video_id in seen_video_ids:
            continue
        if not _is_published_today(video, today_kst):
            continue
        seen_video_ids.add(video_id)
        today_videos.append(video)

    return today_videos


def _is_published_today(video: Video, today_kst: date) -> bool:
    """Return whether the video published_at date is today in KST."""

    published_at = _published_at_datetime(video)
    if published_at is None:
        return False
    return published_at.astimezone(KST).date() == today_kst


def _published_at_datetime(video: Video) -> datetime | None:
    """Parse a YouTube published_at value into an aware UTC datetime."""

    raw_published_at = video.get("published_at")
    if not isinstance(raw_published_at, str) or not raw_published_at.strip():
        return None

    normalized = raw_published_at.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning(
            "published_at 날짜 형식을 해석하지 못했습니다. video_id=%s, published_at=%s",
            video.get("video_id", ""),
            raw_published_at,
        )
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _attach_video_metadata(analysis: Analysis, video: Video, test_mode: str) -> Analysis:
    """Attach video metadata to one analysis result for email display."""

    enriched = dict(analysis)
    enriched.setdefault("video_id", video.get("video_id", ""))
    enriched.setdefault("playlist_id", video.get("playlist_id", ""))
    enriched.setdefault("video_title", video.get("title", ""))
    enriched.setdefault("video_url", video.get("url", ""))
    enriched.setdefault("published_at", video.get("published_at", ""))
    enriched.setdefault("channel_title", video.get("channel_title", ""))
    if test_mode in {"today", "latest_one"}:
        enriched.setdefault("test_mode", test_mode)
    return enriched


def _ensure_video_url(video: Video) -> Video:
    """Ensure a video dictionary has a YouTube watch URL."""

    if video.get("url"):
        return video

    video_with_url = dict(video)
    video_id = video_with_url.get("video_id", "")
    if video_id:
        video_with_url["url"] = f"https://www.youtube.com/watch?v={video_id}"
    return video_with_url


def _filter_new_unique_videos(
    videos: list[Video],
    processed_video_ids: set[str],
) -> list[Video]:
    """Remove already processed videos and duplicate video IDs."""

    seen_video_ids: set[str] = set()
    new_videos: list[Video] = []

    for video in videos:
        video_id = video.get("video_id")
        if not video_id:
            continue
        if video_id in processed_video_ids:
            continue
        if video_id in seen_video_ids:
            logger.info(
                "중복 영상이라 한 번만 분석합니다. video_id=%s. "
                "초보자 안내: 같은 영상이 여러 재생목록에 있을 수 있습니다.",
                video_id,
            )
            continue

        seen_video_ids.add(video_id)
        new_videos.append(video)

    return new_videos


def _configure_logging() -> None:
    """Configure beginner-friendly console logging."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


if __name__ == "__main__":
    sys.exit(main())
