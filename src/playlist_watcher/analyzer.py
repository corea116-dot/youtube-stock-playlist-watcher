"""Analyze video text with OpenAI and return structured stock mentions."""

from __future__ import annotations

import json
import logging
from typing import Any

from playlist_watcher.config import AppConfig, load_config


logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended_stocks": {
            "type": "array",
            "description": "Stocks the video explicitly presents as recommended.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "ticker": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "ticker", "reason", "evidence"],
                "additionalProperties": False,
            },
        },
        "watchlist_stocks": {
            "type": "array",
            "description": "Stocks the video explicitly mentions as watchlist or interest items.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "ticker": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "ticker", "reason", "evidence"],
                "additionalProperties": False,
            },
        },
        "sectors": {
            "type": "array",
            "description": "Sectors or themes explicitly mentioned in the video.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "reason", "evidence"],
                "additionalProperties": False,
            },
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the video content relevant to mentioned stocks and sectors.",
        },
        "uncertain_items": {
            "type": "array",
            "description": "Items that were unclear or not explicitly supported by the source text.",
            "items": {"type": "string"},
        },
        "source_limitations": {
            "type": "string",
            "description": "Any limitations in the provided title, description, or transcript.",
        },
        "not_investment_advice": {
            "type": "string",
            "description": "A clear statement that this is a content summary, not investment advice.",
        },
    },
    "required": [
        "recommended_stocks",
        "watchlist_stocks",
        "sectors",
        "summary",
        "uncertain_items",
        "source_limitations",
        "not_investment_advice",
    ],
    "additionalProperties": False,
}


class AnalysisError(RuntimeError):
    """Raised when OpenAI analysis cannot be completed."""


def analyze_video_content(
    title: str,
    description: str,
    transcript_text: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Analyze video title, description, and transcript with OpenAI.

    The result is a structured dictionary containing stocks, sectors, reasons,
    evidence, uncertainty notes, and a non-investment-advice disclaimer.
    """

    app_config = config or load_config()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AnalysisError(
            "OpenAI 패키지를 찾을 수 없습니다.\n"
            "초보자 안내: 가상환경을 켠 뒤 `pip install -e .` 명령어로 "
            "프로젝트 의존성을 설치하세요."
        ) from exc

    client = OpenAI(api_key=app_config.openai_api_key)
    prompt_input = _build_prompt_input(title, description, transcript_text)

    try:
        response = client.responses.create(
            model=app_config.openai_model,
            input=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": prompt_input},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "video_stock_analysis",
                    "description": "Structured summary of stocks and sectors mentioned in a video.",
                    "strict": True,
                    "schema": ANALYSIS_SCHEMA,
                }
            },
        )
    except Exception as exc:
        logger.warning(
            "OpenAI 분석 요청에 실패했습니다. 이유=%s. "
            "초보자 안내: OPENAI_API_KEY가 맞는지, OPENAI_MODEL 값이 사용 가능한지, "
            "네트워크 연결이 정상인지 확인하세요.",
            exc,
        )
        raise AnalysisError(
            "OpenAI 분석 요청에 실패했습니다. API 키, 모델 이름, 네트워크 상태를 확인하세요."
        ) from exc

    try:
        return _parse_structured_response(response)
    except (AttributeError, json.JSONDecodeError, TypeError) as exc:
        raise AnalysisError(
            "OpenAI 분석 결과를 JSON으로 읽지 못했습니다. "
            "초보자 안내: 모델 응답 형식이 예상과 다를 수 있습니다."
        ) from exc


def _system_prompt() -> str:
    """Return the fixed system prompt for safe content summarization."""

    return (
        "You summarize investment-related YouTube content without creating new "
        "investment advice. Extract only what is explicitly mentioned in the "
        "provided title, description, and transcript. Do not invent tickers, "
        "recommendations, reasons, prices, targets, or predictions. If something "
        "is unclear, put it in uncertain_items. If the source does not clearly "
        "state a ticker, leave ticker as an empty string. Write the result in Korean."
    )


def _build_prompt_input(
    title: str,
    description: str,
    transcript_text: str | None,
) -> str:
    """Build the user input sent to OpenAI."""

    transcript_section = transcript_text if transcript_text else "자막 없음"
    return (
        "아래 YouTube 영상 정보를 분석하세요.\n\n"
        "반드시 지켜야 할 규칙:\n"
        "- 투자 조언을 새로 만들지 마세요.\n"
        "- 영상에 실제로 언급된 종목, 관심 종목, 섹터, 이유만 정리하세요.\n"
        "- 근거 문장은 title/description/transcript 안에서 확인 가능한 내용만 쓰세요.\n"
        "- 불확실하면 추측하지 말고 uncertain_items에 적으세요.\n\n"
        f"제목:\n{title}\n\n"
        f"설명:\n{description}\n\n"
        f"자막:\n{transcript_section}\n"
    )


def _parse_structured_response(response: Any) -> dict[str, Any]:
    """Parse the OpenAI response into a dictionary."""

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        parsed = json.loads(output_text)
        if isinstance(parsed, dict):
            return parsed

    output_parsed = getattr(response, "output_parsed", None)
    if isinstance(output_parsed, dict):
        return output_parsed

    raise TypeError("OpenAI response did not contain structured output text.")

