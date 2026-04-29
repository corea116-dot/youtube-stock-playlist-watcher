"""Analyze video text with Google Gemini and return structured stock mentions."""

from __future__ import annotations

import json
import logging
from typing import Any

from playlist_watcher.config import AppConfig, load_config


logger = logging.getLogger(__name__)

YOUTUBE_URL_PROMPT = (
    "이 YouTube 영상의 실제 영상/음성 내용을 바탕으로, 영상에서 언급된 추천 종목, "
    "관심 종목, 섹터, 언급 이유, 리스크를 추출하세요. 영상에서 확인할 수 없는 내용은 "
    "추측하지 마세요. 투자 조언처럼 단정하지 말고 '영상에서 언급됨' 기준으로 정리하세요."
)


class AnalysisError(RuntimeError):
    """Raised when Gemini analysis cannot be requested."""


def analyze_video(
    video: dict,
    transcript_text: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Analyze one video with Gemini using transcript, URL, or metadata fallback."""

    app_config = config or load_config()

    if transcript_text:
        analysis, _ = _analyze_with_text(
            prompt=_build_transcript_prompt(video, transcript_text),
            config=app_config,
            analysis_basis="transcript",
        )
        return analysis

    video_url = _string_value(video.get("url"))
    if video_url:
        try:
            analysis, usable = _analyze_with_youtube_url(video, app_config)
            if usable:
                return analysis
            logger.warning(
                "Gemini YouTube URL 직접 분석 응답을 사용할 수 없어 fallback으로 진행합니다. video_id=%s",
                video.get("video_id", ""),
            )
        except AnalysisError as exc:
            logger.warning(
                "Gemini YouTube URL 직접 분석에 실패해 fallback으로 진행합니다. video_id=%s, 이유=%s",
                video.get("video_id", ""),
                exc,
            )

    comments = _safe_get_comments(video)
    fallback_basis = "metadata_plus_comments" if comments else "metadata_only"
    analysis, _ = _analyze_with_text(
        prompt=_build_metadata_fallback_prompt(video, comments),
        config=app_config,
        analysis_basis=fallback_basis,
    )
    return analysis


def analyze_video_content(
    title: str,
    description: str,
    transcript_text: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper used by older tests/callers."""

    return analyze_video(
        {"title": title, "description": description, "tags": [], "url": ""},
        transcript_text,
        config,
    )


def _analyze_with_text(
    prompt: str,
    config: AppConfig,
    analysis_basis: str,
) -> tuple[dict[str, Any], bool]:
    """Ask Gemini to analyze text-only input."""

    genai, types = _load_gemini_modules()
    try:
        client = genai.Client(api_key=config.gemini_api_key)
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.warning(
            "Gemini 분석 요청에 실패했습니다. 이유=%s. "
            "초보자 안내: GEMINI_API_KEY, GEMINI_MODEL, 네트워크 상태를 확인하세요.",
            exc,
        )
        raise AnalysisError("Gemini 분석 요청에 실패했습니다.") from exc

    return _parse_gemini_response(response, analysis_basis)


def _analyze_with_youtube_url(
    video: dict,
    config: AppConfig,
) -> tuple[dict[str, Any], bool]:
    """Ask Gemini to analyze a public YouTube URL directly."""

    genai, types = _load_gemini_modules()
    video_url = _string_value(video.get("url"))
    prompt = _build_youtube_url_prompt(video)

    try:
        client = genai.Client(api_key=config.gemini_api_key)
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=types.Content(
                parts=[
                    types.Part(file_data=types.FileData(file_uri=video_url)),
                    types.Part(text=prompt),
                ]
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        raise AnalysisError("Gemini YouTube URL 직접 분석 요청에 실패했습니다.") from exc

    return _parse_gemini_response(response, "gemini_youtube_url")


def _load_gemini_modules() -> tuple[Any, Any]:
    """Import google-genai modules with a beginner-friendly error."""

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AnalysisError(
            "Google Gemini 패키지 google-genai를 찾을 수 없습니다.\n"
            "초보자 안내: 가상환경을 켠 뒤 `pip install -e .` 명령어로 "
            "프로젝트 의존성을 설치하세요."
        ) from exc

    return genai, types


def _build_transcript_prompt(video: dict, transcript_text: str) -> str:
    """Build a prompt for transcript-based analysis."""

    return _base_prompt(
        source_label="자막 기반 분석",
        source_text=(
            f"제목:\n{_string_value(video.get('title'))}\n\n"
            f"설명:\n{_string_value(video.get('description'))}\n\n"
            f"태그:\n{', '.join(_list_of_strings(video.get('tags')))}\n\n"
            f"자막:\n{transcript_text}\n"
        ),
    )


def _build_youtube_url_prompt(video: dict) -> str:
    """Build a prompt for direct YouTube URL analysis."""

    return _base_prompt(
        source_label="Gemini YouTube URL 직접 분석",
        source_text=(
            f"{YOUTUBE_URL_PROMPT}\n\n"
            f"참고 메타데이터:\n"
            f"제목: {_string_value(video.get('title'))}\n"
            f"설명: {_string_value(video.get('description'))}\n"
            f"태그: {', '.join(_list_of_strings(video.get('tags')))}\n"
        ),
    )


def _build_metadata_fallback_prompt(video: dict, comments: list[str]) -> str:
    """Build a prompt for metadata/comments fallback analysis."""

    comments_section = "\n".join(f"- {comment}" for comment in comments)
    if comments:
        source_label = "제목/설명/태그/댓글 기반 제한 분석"
        comments_notice = (
            "댓글은 영상 실제 발언이 아니라 시청자 반응/보조 단서입니다. "
            "댓글 내용을 영상 발언처럼 단정하지 마세요."
        )
    else:
        source_label = "제목/설명/태그 기반 제한 분석"
        comments_notice = "댓글을 가져오지 못했거나 댓글이 없어 사용하지 않습니다."

    return _base_prompt(
        source_label=source_label,
        source_text=(
            "영상 본문 직접 분석에 실패했으므로 제한된 보조 정보만 사용합니다.\n"
            f"{comments_notice}\n\n"
            f"제목:\n{_string_value(video.get('title'))}\n\n"
            f"설명:\n{_string_value(video.get('description'))}\n\n"
            f"채널:\n{_string_value(video.get('channel_title'))}\n\n"
            f"태그:\n{', '.join(_list_of_strings(video.get('tags')))}\n\n"
            f"댓글:\n{comments_section if comments_section else '댓글 없음'}\n"
        ),
    )


def _base_prompt(source_label: str, source_text: str) -> str:
    """Build the shared analyzer prompt."""

    return (
        "You summarize investment-related YouTube content without creating new investment advice.\n"
        "반드시 지켜야 할 규칙:\n"
        "- 영상 또는 제공된 자료에 실제로 언급된 종목, 관심 종목, 섹터, 이유만 정리하세요.\n"
        "- 영상에서 확인할 수 없는 종목/섹터/가격/목표가/전망은 추측하지 마세요.\n"
        "- 투자 조언처럼 단정하지 말고 '영상에서 언급됨' 기준으로 정리하세요.\n"
        "- 명확히 언급된 종목/섹터가 없으면 summary에 왜 없는지 짧게 설명하세요.\n"
        "- 분석 실패 원인은 source_limitations에 짧게만 적으세요.\n"
        "- 반드시 JSON만 반환하세요.\n\n"
        f"분석 기준: {source_label}\n\n"
        f"JSON 구조 예시:\n{json.dumps(_empty_analysis(), ensure_ascii=False, indent=2)}\n\n"
        f"자료:\n{source_text}\n"
    )


def _parse_gemini_response(
    response: Any,
    analysis_basis: str,
) -> tuple[dict[str, Any], bool]:
    """Parse Gemini response text into the existing analysis dictionary shape."""

    response_text = getattr(response, "text", None)
    if not isinstance(response_text, str) or not response_text.strip():
        return _fallback_analysis("Gemini 응답이 비어 있습니다.", analysis_basis), False

    try:
        parsed = json.loads(_strip_json_fence(response_text))
    except json.JSONDecodeError:
        logger.warning(
            "Gemini 응답이 JSON 형식이 아니어서 fallback 결과로 처리합니다. "
            "초보자 안내: 모델 응답이 예상 형식과 다를 수 있습니다."
        )
        return _fallback_analysis("Gemini 응답이 JSON 형식이 아닙니다.", analysis_basis), False

    if not isinstance(parsed, dict):
        return _fallback_analysis("Gemini 응답 JSON이 객체 형식이 아닙니다.", analysis_basis), False

    return _normalize_analysis(parsed, analysis_basis), True


def _normalize_analysis(parsed: dict[str, Any], analysis_basis: str) -> dict[str, Any]:
    """Ensure the analysis dictionary has the expected keys."""

    normalized = _empty_analysis()
    recommended_stocks = _list_value(parsed.get("recommended_stocks"))
    watchlist_stocks = _list_value(parsed.get("watchlist_stocks"))
    sectors = _list_value(parsed.get("sectors"))
    normalized.update(
        {
            "recommended_stocks": recommended_stocks,
            "watchlist_stocks": watchlist_stocks,
            "mentioned_stocks": _list_value(parsed.get("mentioned_stocks"))
            or recommended_stocks
            + watchlist_stocks,
            "sectors": sectors,
            "mentioned_sectors": _list_value(parsed.get("mentioned_sectors"))
            or sectors,
            "risks": _list_value(parsed.get("risks")),
            "summary": _string_value(parsed.get("summary")),
            "confidence": _string_value(parsed.get("confidence")) or "low",
            "uncertain_items": _list_value(parsed.get("uncertain_items")),
            "source_limitations": _short_text(
                _string_value(parsed.get("source_limitations"))
            ),
            "not_investment_advice": _string_value(
                parsed.get("not_investment_advice")
            )
            or "이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
            "analysis_basis": analysis_basis,
        }
    )

    if not _has_mentions(normalized) and not normalized["summary"]:
        normalized["summary"] = "제공된 자료에서 명확히 언급된 종목 또는 섹터를 확인하지 못했습니다."

    return normalized


def _fallback_analysis(reason: str, analysis_basis: str) -> dict[str, Any]:
    """Return a safe empty analysis when Gemini returns unusable output."""

    analysis = _empty_analysis()
    analysis["summary"] = "제공된 자료에서 명확히 언급된 종목 또는 섹터를 확인하지 못했습니다."
    analysis["uncertain_items"] = [_short_text(reason)]
    analysis["source_limitations"] = _short_text(reason)
    analysis["analysis_basis"] = analysis_basis
    analysis["confidence"] = "low"
    return analysis


def _safe_get_comments(video: dict) -> list[str]:
    """Fetch comments without letting comment failures stop analysis."""

    video_id = _string_value(video.get("video_id"))
    if not video_id:
        return []

    try:
        from playlist_watcher.youtube import get_video_comments

        return get_video_comments(video_id)
    except Exception as exc:
        logger.warning(
            "댓글 fallback 정보를 가져오지 못했습니다. video_id=%s, 이유=%s",
            video_id,
            exc,
        )
        return []


def _empty_analysis() -> dict[str, Any]:
    """Return the existing analysis result structure with empty values."""

    return {
        "analysis_basis": "",
        "recommended_stocks": [],
        "watchlist_stocks": [],
        "mentioned_stocks": [],
        "sectors": [],
        "mentioned_sectors": [],
        "risks": [],
        "summary": "",
        "confidence": "low",
        "uncertain_items": [],
        "source_limitations": "",
        "not_investment_advice": "이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
    }


def _has_mentions(analysis: dict[str, Any]) -> bool:
    """Return whether the analysis contains any stock or sector mention."""

    return bool(
        analysis.get("recommended_stocks")
        or analysis.get("watchlist_stocks")
        or analysis.get("mentioned_stocks")
        or analysis.get("sectors")
        or analysis.get("mentioned_sectors")
    )


def _strip_json_fence(value: str) -> str:
    """Remove common Markdown JSON fences if the model includes them."""

    stripped = value.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _list_value(value: Any) -> list[Any]:
    """Return value if it is a list, otherwise an empty list."""

    return value if isinstance(value, list) else []


def _list_of_strings(value: Any) -> list[str]:
    """Return string items from a list-like value."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_value(value: Any) -> str:
    """Return value if it is a string, otherwise an empty string."""

    return value if isinstance(value, str) else ""


def _short_text(value: str, limit: int = 160) -> str:
    """Keep failure reasons short for email display."""

    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"
