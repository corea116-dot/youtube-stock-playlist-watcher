"""Analyze video text with Google Gemini and return structured stock mentions."""

from __future__ import annotations

import json
import logging
from typing import Any

from playlist_watcher.config import AppConfig, load_config


logger = logging.getLogger(__name__)


class AnalysisError(RuntimeError):
    """Raised when Gemini analysis cannot be requested."""


def analyze_video(
    video: dict,
    transcript_text: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Analyze one video with Gemini and return the existing JSON structure."""

    app_config = config or load_config()

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AnalysisError(
            "Google Gemini 패키지 google-genai를 찾을 수 없습니다.\n"
            "초보자 안내: 가상환경을 켠 뒤 `pip install -e .` 명령어로 "
            "프로젝트 의존성을 설치하세요."
        ) from exc

    prompt = _build_prompt_input(
        title=_string_value(video.get("title")),
        description=_string_value(video.get("description")),
        transcript_text=transcript_text,
    )

    try:
        client = genai.Client(api_key=app_config.gemini_api_key)
        response = client.models.generate_content(
            model=app_config.gemini_model,
            contents=f"{_system_prompt()}\n\n{prompt}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.warning(
            "Gemini 분석 요청에 실패했습니다. 이유=%s. "
            "초보자 안내: GEMINI_API_KEY가 맞는지, GEMINI_MODEL 값이 사용 가능한지, "
            "네트워크 연결이 정상인지 확인하세요.",
            exc,
        )
        raise AnalysisError(
            "Gemini 분석 요청에 실패했습니다. API 키, 모델 이름, 네트워크 상태를 확인하세요."
        ) from exc

    return _parse_gemini_response(response)


def analyze_video_content(
    title: str,
    description: str,
    transcript_text: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper used by the current main workflow."""

    return analyze_video(
        {"title": title, "description": description},
        transcript_text,
        config,
    )


def _system_prompt() -> str:
    """Return the fixed system prompt for safe content summarization."""

    return (
        "You summarize investment-related YouTube content without creating new "
        "investment advice. Extract only what is explicitly mentioned in the "
        "provided title, description, and transcript. Do not invent tickers, "
        "recommendations, reasons, prices, targets, or predictions. If something "
        "is unclear, put it in uncertain_items. If the source does not clearly "
        "state a ticker, leave ticker as an empty string. Write valid JSON only. "
        "Write the result in Korean."
    )


def _build_prompt_input(
    title: str,
    description: str,
    transcript_text: str | None,
) -> str:
    """Build the user input sent to Gemini."""

    transcript_section = transcript_text if transcript_text else "자막 없음"
    return (
        "아래 YouTube 영상 정보를 분석하세요.\n\n"
        "반드시 지켜야 할 규칙:\n"
        "- 투자 조언을 새로 만들지 마세요.\n"
        "- 영상에 실제로 언급된 종목, 관심 종목, 섹터, 이유만 정리하세요.\n"
        "- 근거 문장은 title/description/transcript 안에서 확인 가능한 내용만 쓰세요.\n"
        "- 불확실하면 추측하지 말고 uncertain_items에 적으세요.\n"
        "- 반드시 아래 JSON 구조로만 답하세요.\n\n"
        f"JSON 구조:\n{json.dumps(_empty_analysis(), ensure_ascii=False, indent=2)}\n\n"
        f"제목:\n{title}\n\n"
        f"설명:\n{description}\n\n"
        f"자막:\n{transcript_section}\n"
    )


def _parse_gemini_response(response: Any) -> dict[str, Any]:
    """Parse Gemini response text into the existing analysis dictionary shape."""

    response_text = getattr(response, "text", None)
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning(
            "Gemini 응답이 비어 있어 빈 분석 결과로 처리합니다. "
            "초보자 안내: 일시적인 응답 문제일 수 있습니다."
        )
        return _fallback_analysis("Gemini 응답이 비어 있습니다.")

    try:
        parsed = json.loads(_strip_json_fence(response_text))
    except json.JSONDecodeError:
        logger.warning(
            "Gemini 응답이 JSON 형식이 아니어서 빈 분석 결과로 처리합니다. "
            "초보자 안내: 모델 응답이 예상 형식과 다를 수 있습니다."
        )
        return _fallback_analysis("Gemini 응답이 JSON 형식이 아닙니다.")

    if not isinstance(parsed, dict):
        return _fallback_analysis("Gemini 응답 JSON이 객체 형식이 아닙니다.")

    return _normalize_analysis(parsed)


def _normalize_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    """Ensure the analysis dictionary has the expected keys."""

    normalized = _empty_analysis()
    normalized.update(
        {
            "recommended_stocks": _list_value(parsed.get("recommended_stocks")),
            "watchlist_stocks": _list_value(parsed.get("watchlist_stocks")),
            "sectors": _list_value(parsed.get("sectors")),
            "summary": _string_value(parsed.get("summary")),
            "uncertain_items": _list_value(parsed.get("uncertain_items")),
            "source_limitations": _string_value(parsed.get("source_limitations")),
            "not_investment_advice": _string_value(
                parsed.get("not_investment_advice")
            )
            or "이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
        }
    )
    return normalized


def _fallback_analysis(reason: str) -> dict[str, Any]:
    """Return a safe empty analysis when Gemini returns unusable output."""

    analysis = _empty_analysis()
    analysis["uncertain_items"] = [reason]
    analysis["source_limitations"] = reason
    return analysis


def _empty_analysis() -> dict[str, Any]:
    """Return the existing analysis result structure with empty values."""

    return {
        "recommended_stocks": [],
        "watchlist_stocks": [],
        "sectors": [],
        "summary": "",
        "uncertain_items": [],
        "source_limitations": "",
        "not_investment_advice": "이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
    }


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


def _string_value(value: Any) -> str:
    """Return value if it is a string, otherwise an empty string."""

    return value if isinstance(value, str) else ""
