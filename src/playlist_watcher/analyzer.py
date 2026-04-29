"""Analyze public YouTube URLs with Google Gemini."""

from __future__ import annotations

import json
import logging
from typing import Any

from playlist_watcher.config import AppConfig, load_config


logger = logging.getLogger(__name__)

ANALYSIS_BASIS = "gemini_youtube_url"
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed", "uncertain"}
VALID_CONFIDENCE = {"high", "medium", "low"}

KNOWN_STOCK_NAMES = {
    "삼성전자": {"ticker": "005930", "market": "KRX"},
    "SK하이닉스": {"ticker": "000660", "market": "KRX"},
}
KNOWN_SECTOR_NAMES = (
    "반도체",
    "자동차",
    "화학",
    "철강",
    "조선",
    "통신",
    "필수소비재",
    "게임",
)


class AnalysisError(RuntimeError):
    """Raised when Gemini analysis cannot be requested."""


def analyze_video(
    video: dict,
    transcript_text: str | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Analyze one video with Gemini YouTube URL direct input.

    ``transcript_text`` is kept only for backward compatibility. The current
    workflow does not fetch or use YouTube transcripts because they are
    unreliable in GitHub Actions.
    """

    del transcript_text
    app_config = config or load_config()
    video_url = _string_value(video.get("url"))
    if not video_url:
        logger.warning(
            "Gemini YouTube URL 직접 분석을 할 수 없습니다. 이유=video['url'] 값이 비어 있습니다. video_id=%s",
            video.get("video_id", ""),
        )
        return _fallback_analysis("영상 URL이 없어 Gemini YouTube URL 직접 분석을 할 수 없습니다.", video)

    try:
        analysis, _ = _analyze_with_youtube_url(video, app_config)
        return analysis
    except AnalysisError as exc:
        logger.warning(
            "Gemini YouTube URL 직접 분석에 실패했습니다. video_id=%s, 이유=%s",
            video.get("video_id", ""),
            exc,
        )
        return _fallback_analysis(str(exc), video)


def analyze_video_content(
    title: str,
    description: str,
    transcript_text: str | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper used by older callers."""

    del transcript_text
    return analyze_video(
        {"title": title, "description": description, "tags": [], "url": ""},
        None,
        config,
    )


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
            config=_build_generate_content_config(types),
        )
    except Exception as exc:
        raise AnalysisError("Gemini YouTube URL 직접 분석 요청에 실패했습니다.") from exc

    return _parse_gemini_response(response, video)


def _build_generate_content_config(types: Any) -> Any:
    """Build Gemini generation config with structured JSON output when supported."""

    schema = _response_json_schema()
    base_config = {
        "response_mime_type": "application/json",
        "temperature": 0.1,
    }

    for schema_field in ("response_json_schema", "response_schema"):
        try:
            return types.GenerateContentConfig(
                **base_config,
                **{schema_field: schema},
            )
        except TypeError:
            continue

    logger.warning(
        "현재 google-genai 버전에서 response schema 설정을 사용할 수 없어 "
        "JSON mime type과 강화 프롬프트만 사용합니다."
    )
    return types.GenerateContentConfig(**base_config)


def _load_gemini_modules() -> tuple[Any, Any]:
    """Import google-genai modules with a beginner-friendly error."""

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AnalysisError(
            "Google Gemini 패키지 google-genai를 찾을 수 없습니다. "
            "초보자 안내: 가상환경을 켠 뒤 `pip install -e .` 명령어로 "
            "프로젝트 의존성을 설치하세요."
        ) from exc

    return genai, types


def _build_youtube_url_prompt(video: dict) -> str:
    """Build a strict prompt for direct YouTube URL analysis."""

    expected_json = _prompt_analysis_schema(video)
    return (
        "당신은 public YouTube 영상을 직접 분석해 영상에서 실제로 언급된 종목과 섹터를 "
        "구조화하는 도구입니다. 투자 조언을 만들지 말고 영상에서 언급된 내용만 정리하세요.\n\n"
        "반드시 지켜야 할 핵심 규칙:\n"
        "- 이 YouTube 영상의 실제 영상/음성 내용을 바탕으로, 영상에서 언급된 추천 종목, 관심 종목, 섹터, 언급 이유, 리스크를 추출하세요.\n"
        "- 영상에서 확인할 수 없는 내용은 추측하지 마세요.\n"
        "- 투자 조언처럼 단정하지 말고 '영상에서 언급됨' 기준으로 정리하세요.\n"
        "- 반드시 JSON 객체만 반환하세요. Markdown, 설명문, 코드블록은 넣지 마세요.\n"
        "- 영상에서 특정 종목명이 언급되면 반드시 mentioned_stocks 배열에 넣으세요.\n"
        "- 영상에서 특정 산업/테마/섹터가 언급되면 반드시 mentioned_sectors 배열에 넣으세요.\n"
        "- 삼성전자, SK하이닉스처럼 summary에 등장한 종목을 mentioned_stocks에서 누락하지 마세요.\n"
        "- 반도체, 자동차, 화학, 철강, 조선, 통신, 필수소비재, 게임 등 summary에 등장한 섹터를 mentioned_sectors에서 누락하지 마세요.\n"
        "- 단순 언급이어도 sentiment를 neutral 또는 uncertain으로 넣으세요.\n"
        "- 긍정적으로 언급되면 positive, 부정적으로 언급되면 negative, 장단점이 섞이면 mixed로 표시하세요.\n"
        "- reason은 짧고 구체적으로 작성하세요.\n"
        "- risk는 영상에서 언급된 리스크나 불확실성을 짧게 쓰고, 없으면 빈 문자열로 두세요.\n"
        "- confidence는 high, medium, low 중 하나만 쓰세요.\n"
        "- mentioned_stocks, mentioned_sectors는 절대 null로 두지 말고 없으면 []로 반환하세요.\n\n"
        "반환해야 하는 JSON 구조 예시:\n"
        f"{json.dumps(expected_json, ensure_ascii=False, indent=2)}\n\n"
        "참고 메타데이터:\n"
        f"video_title: {_string_value(video.get('title'))}\n"
        f"video_url: {_string_value(video.get('url'))}\n"
        f"channel_title: {_string_value(video.get('channel_title'))}\n"
        f"published_at: {_string_value(video.get('published_at'))}\n"
        f"description: {_short_text(_string_value(video.get('description')), limit=1200)}\n"
        f"tags: {', '.join(_list_of_strings(video.get('tags')))}\n"
    )


def _parse_gemini_response(response: Any, video: dict) -> tuple[dict[str, Any], bool]:
    """Parse Gemini response text into the analysis dictionary shape."""

    response_text = getattr(response, "text", None)
    if not isinstance(response_text, str) or not response_text.strip():
        return _fallback_analysis("Gemini 응답이 비어 있습니다.", video), False

    json_text = _extract_json_object(response_text)
    if not json_text:
        logger.warning("Gemini 응답에서 JSON 객체를 찾지 못해 fallback 결과로 처리합니다.")
        return _fallback_analysis("Gemini 응답에서 JSON 객체를 찾지 못했습니다.", video), False

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning(
            "Gemini 응답 JSON 파싱에 실패해 fallback 결과로 처리합니다. "
            "초보자 안내: 모델 응답이 예상 형식과 다를 수 있습니다."
        )
        return _fallback_analysis("Gemini 응답 JSON 파싱에 실패했습니다.", video), False

    if not isinstance(parsed, dict):
        return _fallback_analysis("Gemini 응답 JSON이 객체 형식이 아닙니다.", video), False

    return _normalize_analysis(parsed, video), True


def _normalize_analysis(parsed: dict[str, Any], video: dict) -> dict[str, Any]:
    """Ensure the analysis dictionary has the expected keys."""

    normalized = _empty_analysis(video)
    normalized.update(
        {
            "video_title": _string_value(parsed.get("video_title"))
            or _string_value(video.get("title")),
            "video_url": _string_value(parsed.get("video_url"))
            or _string_value(video.get("url")),
            "analysis_basis": ANALYSIS_BASIS,
            "summary": _string_value(parsed.get("summary")),
            "market_view": _normalize_market_view(parsed.get("market_view")),
            "mentioned_stocks": _normalize_stock_items(
                _list_value(parsed.get("mentioned_stocks"))
                or _list_value(parsed.get("recommended_stocks"))
                + _list_value(parsed.get("watchlist_stocks"))
            ),
            "mentioned_sectors": _normalize_sector_items(
                _list_value(parsed.get("mentioned_sectors"))
                or _list_value(parsed.get("sectors"))
            ),
            "key_points": _string_list(parsed.get("key_points")),
            "watch_points": _string_list(parsed.get("watch_points")),
            "overall_notes": _string_list(parsed.get("overall_notes")),
            "disclaimer": _string_value(parsed.get("disclaimer"))
            or "이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
            "source_limitations": _short_text(_string_value(parsed.get("source_limitations"))),
            "uncertain_items": _string_list(parsed.get("uncertain_items")),
        }
    )

    _recover_mentions_from_summary(normalized)

    if not normalized["summary"]:
        if normalized["mentioned_stocks"] or normalized["mentioned_sectors"]:
            normalized["summary"] = "영상에서 언급된 종목과 섹터를 구조화했습니다."
        else:
            normalized["summary"] = "영상에서 명확히 구조화할 종목 또는 섹터를 확인하지 못했습니다."

    # Backward-compatible aliases for older callers/email templates.
    normalized["recommended_stocks"] = normalized["mentioned_stocks"]
    normalized["watchlist_stocks"] = []
    normalized["sectors"] = normalized["mentioned_sectors"]
    normalized["risks"] = [
        item.get("risk", "")
        for item in normalized["mentioned_stocks"] + normalized["mentioned_sectors"]
        if item.get("risk")
    ]
    normalized["confidence"] = _overall_confidence(normalized)
    normalized["not_investment_advice"] = normalized["disclaimer"]
    return normalized


def _normalize_market_view(value: Any) -> dict[str, str]:
    """Normalize market_view."""

    if not isinstance(value, dict):
        return {"overall_tone": "uncertain", "reason": ""}
    return {
        "overall_tone": _normalize_sentiment(value.get("overall_tone")),
        "reason": _string_value(value.get("reason")),
    }


def _normalize_stock_items(items: list[Any]) -> list[dict[str, str]]:
    """Normalize mentioned stock rows."""

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _string_value(item.get("name"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        known = KNOWN_STOCK_NAMES.get(name, {})
        normalized.append(
            {
                "name": name,
                "ticker": _string_value(item.get("ticker")) or known.get("ticker", ""),
                "market": _string_value(item.get("market")) or known.get("market", ""),
                "sentiment": _normalize_sentiment(item.get("sentiment")),
                "reason": _string_value(item.get("reason")),
                "risk": _string_value(item.get("risk")),
                "confidence": _normalize_confidence(item.get("confidence")),
            }
        )
    return normalized


def _normalize_sector_items(items: list[Any]) -> list[dict[str, str]]:
    """Normalize mentioned sector rows."""

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _string_value(item.get("name"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "name": name,
                "sentiment": _normalize_sentiment(item.get("sentiment")),
                "reason": _string_value(item.get("reason")),
                "risk": _string_value(item.get("risk")),
                "confidence": _normalize_confidence(item.get("confidence")),
            }
        )
    return normalized


def _recover_mentions_from_summary(analysis: dict[str, Any]) -> None:
    """Recover obvious names from Gemini summary if structured arrays are empty."""

    summary = _string_value(analysis.get("summary"))
    if not summary:
        return

    if not analysis["mentioned_stocks"]:
        recovered_stocks = []
        for name, metadata in KNOWN_STOCK_NAMES.items():
            if name in summary:
                recovered_stocks.append(
                    {
                        "name": name,
                        "ticker": metadata.get("ticker", ""),
                        "market": metadata.get("market", ""),
                        "sentiment": "uncertain",
                        "reason": "요약에는 등장했지만 Gemini 구조화 응답에서 세부 판단이 누락되었습니다.",
                        "risk": "구조화 추출 누락으로 해석에 제한이 있습니다.",
                        "confidence": "low",
                    }
                )
        analysis["mentioned_stocks"] = recovered_stocks

    if not analysis["mentioned_sectors"]:
        recovered_sectors = []
        for name in KNOWN_SECTOR_NAMES:
            if name in summary:
                recovered_sectors.append(
                    {
                        "name": name,
                        "sentiment": "uncertain",
                        "reason": "요약에는 등장했지만 Gemini 구조화 응답에서 세부 판단이 누락되었습니다.",
                        "risk": "구조화 추출 누락으로 해석에 제한이 있습니다.",
                        "confidence": "low",
                    }
                )
        analysis["mentioned_sectors"] = recovered_sectors


def _fallback_analysis(reason: str, video: dict | None = None) -> dict[str, Any]:
    """Return a safe empty analysis when Gemini returns unusable output."""

    analysis = _empty_analysis(video or {})
    analysis["summary"] = "Gemini YouTube URL 직접 분석 결과를 구조화하지 못했습니다."
    analysis["overall_notes"] = [_short_text(reason)]
    analysis["source_limitations"] = _short_text(reason)
    analysis["confidence"] = "low"
    return analysis


def _empty_analysis(video: dict | None = None) -> dict[str, Any]:
    """Return the analysis result structure with empty values."""

    video = video or {}
    return {
        "video_title": _string_value(video.get("title")),
        "video_url": _string_value(video.get("url")),
        "analysis_basis": ANALYSIS_BASIS,
        "summary": "",
        "market_view": {"overall_tone": "uncertain", "reason": ""},
        "mentioned_stocks": [],
        "mentioned_sectors": [],
        "key_points": [],
        "watch_points": [],
        "overall_notes": [],
        "disclaimer": "이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
        "recommended_stocks": [],
        "watchlist_stocks": [],
        "sectors": [],
        "risks": [],
        "confidence": "low",
        "uncertain_items": [],
        "source_limitations": "",
        "not_investment_advice": "이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
    }


def _prompt_analysis_schema(video: dict) -> dict[str, Any]:
    """Return the exact JSON schema requested from Gemini."""

    return {
        "video_title": _string_value(video.get("title")),
        "video_url": _string_value(video.get("url")),
        "analysis_basis": ANALYSIS_BASIS,
        "summary": "",
        "market_view": {
            "overall_tone": "positive | negative | neutral | mixed | uncertain",
            "reason": "",
        },
        "mentioned_stocks": [
            {
                "name": "",
                "ticker": "",
                "market": "",
                "sentiment": "positive | negative | neutral | mixed | uncertain",
                "reason": "",
                "risk": "",
                "confidence": "high | medium | low",
            }
        ],
        "mentioned_sectors": [
            {
                "name": "",
                "sentiment": "positive | negative | neutral | mixed | uncertain",
                "reason": "",
                "risk": "",
                "confidence": "high | medium | low",
            }
        ],
        "key_points": [],
        "watch_points": [],
        "overall_notes": [],
        "disclaimer": "이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
    }


def _response_json_schema() -> dict[str, Any]:
    """Return a JSON Schema for Gemini structured output."""

    sentiment_schema = {
        "type": "string",
        "enum": ["positive", "negative", "neutral", "mixed", "uncertain"],
    }
    confidence_schema = {
        "type": "string",
        "enum": ["high", "medium", "low"],
    }
    stock_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "ticker": {"type": "string"},
            "market": {"type": "string"},
            "sentiment": sentiment_schema,
            "reason": {"type": "string"},
            "risk": {"type": "string"},
            "confidence": confidence_schema,
        },
        "required": [
            "name",
            "ticker",
            "market",
            "sentiment",
            "reason",
            "risk",
            "confidence",
        ],
        "propertyOrdering": [
            "name",
            "ticker",
            "market",
            "sentiment",
            "reason",
            "risk",
            "confidence",
        ],
    }
    sector_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "sentiment": sentiment_schema,
            "reason": {"type": "string"},
            "risk": {"type": "string"},
            "confidence": confidence_schema,
        },
        "required": ["name", "sentiment", "reason", "risk", "confidence"],
        "propertyOrdering": ["name", "sentiment", "reason", "risk", "confidence"],
    }
    return {
        "type": "object",
        "properties": {
            "video_title": {"type": "string"},
            "video_url": {"type": "string"},
            "analysis_basis": {"type": "string", "enum": [ANALYSIS_BASIS]},
            "summary": {"type": "string"},
            "market_view": {
                "type": "object",
                "properties": {
                    "overall_tone": sentiment_schema,
                    "reason": {"type": "string"},
                },
                "required": ["overall_tone", "reason"],
                "propertyOrdering": ["overall_tone", "reason"],
            },
            "mentioned_stocks": {"type": "array", "items": stock_schema},
            "mentioned_sectors": {"type": "array", "items": sector_schema},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "watch_points": {"type": "array", "items": {"type": "string"}},
            "overall_notes": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
        },
        "required": [
            "video_title",
            "video_url",
            "analysis_basis",
            "summary",
            "market_view",
            "mentioned_stocks",
            "mentioned_sectors",
            "key_points",
            "watch_points",
            "overall_notes",
            "disclaimer",
        ],
        "propertyOrdering": [
            "video_title",
            "video_url",
            "analysis_basis",
            "summary",
            "market_view",
            "mentioned_stocks",
            "mentioned_sectors",
            "key_points",
            "watch_points",
            "overall_notes",
            "disclaimer",
        ],
    }


def _extract_json_object(value: str) -> str:
    """Extract the first JSON object from plain text or Markdown fences."""

    stripped = _strip_json_fence(value)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(stripped)):
        character = stripped[index]
        if in_string:
            if escape:
                escape = False
            elif character == "\\":
                escape = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    return ""


def _strip_json_fence(value: str) -> str:
    """Remove common Markdown JSON fences if the model includes them."""

    stripped = value.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _normalize_sentiment(value: Any) -> str:
    """Normalize sentiment labels."""

    sentiment = _string_value(value).lower()
    return sentiment if sentiment in VALID_SENTIMENTS else "uncertain"


def _normalize_confidence(value: Any) -> str:
    """Normalize confidence labels."""

    confidence = _string_value(value).lower()
    return confidence if confidence in VALID_CONFIDENCE else "low"


def _overall_confidence(analysis: dict[str, Any]) -> str:
    """Return an overall confidence from item-level confidence values."""

    confidences = [
        item.get("confidence", "low")
        for item in analysis.get("mentioned_stocks", []) + analysis.get("mentioned_sectors", [])
        if isinstance(item, dict)
    ]
    if not confidences:
        return "low"
    if "low" in confidences:
        return "low"
    if "medium" in confidences:
        return "medium"
    return "high"


def _list_value(value: Any) -> list[Any]:
    """Return value if it is a list, otherwise an empty list."""

    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    """Return stripped string items from a list-like value."""

    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _list_of_strings(value: Any) -> list[str]:
    """Return string items from a list-like value."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_value(value: Any) -> str:
    """Return a stripped string, otherwise an empty string."""

    return value.strip() if isinstance(value, str) else ""


def _short_text(value: str, limit: int = 160) -> str:
    """Keep failure reasons short for email display."""

    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"
