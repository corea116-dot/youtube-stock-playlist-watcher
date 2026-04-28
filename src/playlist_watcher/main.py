"""Command-line entry point for the YouTube stock playlist watcher."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any

from playlist_watcher.analyzer import analyze_video_content
from playlist_watcher.config import AppConfig, load_config
from playlist_watcher.emailer import _build_email_message, _send_message
from playlist_watcher.state import load_processed_video_ids, mark_processed
from playlist_watcher.transcript import get_transcript_text
from playlist_watcher.youtube import get_latest_playlist_videos


logger = logging.getLogger(__name__)

Video = dict[str, str]
Analysis = dict[str, Any]


def main() -> int:
    """Run the watcher from the command line."""

    _configure_logging()
    return run()


def run(
    load_config_fn: Callable[[], AppConfig] = load_config,
    fetch_videos_fn: Callable[[AppConfig], list[Video]] = get_latest_playlist_videos,
    load_processed_ids_fn: Callable[[], set[str]] = load_processed_video_ids,
    get_transcript_fn: Callable[[str], str | None] = get_transcript_text,
    analyze_fn: Callable[[str, str, str | None, AppConfig], Analysis] = analyze_video_content,
    send_email_fn: Callable[[list[Analysis], AppConfig], bool] = None,
    mark_processed_fn: Callable[[str], None] = mark_processed,
) -> int:
    """Run the full watcher workflow.

    Dependency arguments make this function easy to test with mocks, so tests do
    not need real YouTube, OpenAI, or SMTP credentials.
    """

    if send_email_fn is None:
        send_email_fn = _send_analysis_email_with_success

    try:
        config = load_config_fn()
        logger.info("설정값을 읽었습니다. 초보자 안내: 환경변수 로딩이 완료되었습니다.")

        videos = fetch_videos_fn(config)
        logger.info(
            "YouTube 재생목록 %s개에서 최근 영상 %s개를 가져왔습니다.",
            len(config.playlist_ids),
            len(videos),
        )

        processed_video_ids = load_processed_ids_fn()
        new_videos = _filter_new_unique_videos(videos, processed_video_ids)
    except Exception as exc:
        logger.error(
            "초기 실행 준비 중 오류가 발생했습니다. 이유=%s. "
            "초보자 안내: 환경변수와 YouTube API 설정을 확인하세요.",
            exc,
        )
        return 1

    if not new_videos:
        logger.info("No new videos - 새 영상이 없어 이메일을 보내지 않고 종료합니다.")
        return 0

    logger.info("새 영상 %s개를 처리합니다.", len(new_videos))
    analyses: list[Analysis] = []
    analyzed_video_ids: list[str] = []

    for video in new_videos:
        video_id = video["video_id"]
        logger.info(
            "영상 처리를 시작합니다. playlist_id=%s, video_id=%s, 제목=%s",
            video.get("playlist_id", ""),
            video_id,
            video.get("title", ""),
        )

        try:
            transcript_text = get_transcript_fn(video_id)
        except Exception as exc:
            logger.warning(
                "자막 수집 중 오류가 발생했지만 계속 진행합니다. video_id=%s, 이유=%s. "
                "초보자 안내: 자막이 없어도 제목/설명만으로 분석을 시도합니다.",
                video_id,
                exc,
            )
            transcript_text = None

        try:
            analysis = analyze_fn(
                video.get("title", ""),
                video.get("description", ""),
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

        enriched_analysis = _attach_video_metadata(analysis, video)
        analyses.append(enriched_analysis)
        analyzed_video_ids.append(video_id)
        logger.info("영상 분석을 완료했습니다. video_id=%s", video_id)

    if not analyses:
        logger.info(
            "분석에 성공한 새 영상이 없어 이메일을 보내지 않고 종료합니다. "
            "처리 완료 기록도 추가하지 않습니다."
        )
        return 0

    email_sent = send_email_fn(analyses, config)
    if not email_sent:
        logger.warning(
            "이메일 발송이 실패했으므로 processed_videos.json에 처리 완료로 기록하지 않습니다."
        )
        return 1

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
        logger.info("보낼 분석 결과가 없어 이메일을 보내지 않습니다.")
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

    logger.info("이메일 발송에 성공했습니다. 수신자=%s", config.email_to)
    return True


def _attach_video_metadata(analysis: Analysis, video: Video) -> Analysis:
    """Attach video metadata to one analysis result for email display."""

    enriched = dict(analysis)
    enriched.setdefault("video_id", video.get("video_id", ""))
    enriched.setdefault("playlist_id", video.get("playlist_id", ""))
    enriched.setdefault("video_title", video.get("title", ""))
    enriched.setdefault("video_url", video.get("url", ""))
    enriched.setdefault("published_at", video.get("published_at", ""))
    return enriched


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
