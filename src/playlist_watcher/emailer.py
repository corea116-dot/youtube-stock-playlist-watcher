"""Send video analysis results by email."""

from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from playlist_watcher.config import load_config


logger = logging.getLogger(__name__)

EMAIL_SUBJECT = "[YouTube 종목 분석] 새 영상 분석 결과"


def send_analysis_email(analyses: list[dict]) -> None:
    """Send analysis results by SMTP email.

    If there is no analysis result, no email is sent. SMTP failures are logged
    instead of being raised so the whole program does not stop unexpectedly.
    """

    if not analyses:
        logger.info("이메일을 보내지 않습니다. 이유: 분석 결과가 없습니다.")
        return

    try:
        config = load_config()
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
            "이메일 발송 실패. 원인=%s. "
            "초보자 안내: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO 값이 "
            "맞는지 확인하세요. Gmail을 사용한다면 일반 비밀번호가 아니라 "
            "Gmail App Password가 필요합니다.",
            exc,
        )
        return

    logger.info(
        "이메일 발송 성공. 수신자=%s, 영상 수=%s",
        config.email_to,
        len(analyses),
    )


def _build_email_message(
    analyses: list[dict],
    sender: str,
    recipient: str,
) -> EmailMessage:
    """Build a multipart email with plain text and HTML bodies."""

    message = EmailMessage()
    message["Subject"] = EMAIL_SUBJECT
    message["From"] = sender
    message["To"] = recipient
    message.set_content(_build_plain_text_body(analyses))
    message.add_alternative(_build_html_body(analyses), subtype="html")
    return message


def _send_message(
    message: EmailMessage,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
) -> None:
    """Send an email message through SMTP."""

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        if smtp_port == 587:
            smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)


def _build_plain_text_body(analyses: list[dict]) -> str:
    """Build the plain text fallback body."""

    sections = [
        "YouTube 새 영상 분석 결과",
        "",
        "이 메일은 투자 조언이 아니라 YouTube 영상 내용 요약입니다.",
        "",
    ]

    for index, analysis in enumerate(analyses, start=1):
        sections.extend(
            [
                f"===== 영상 {index} =====",
                f"영상 제목: {_get_value(analysis, 'video_title', 'title')}",
                f"영상 URL: {_get_value(analysis, 'video_url', 'url')}",
                f"분석 기준: {_analysis_basis_label(analysis)}",
                _analysis_basis_notice(analysis),
                f"요약: {_get_value(analysis, 'summary')}",
                "언급 종목:",
                _format_plain_list(_stock_lines(analysis), "명확히 언급된 종목 없음"),
                "언급 섹터:",
                _format_plain_list(_sector_lines(analysis), "명확히 언급된 섹터 없음"),
                "언급 이유:",
                _format_plain_list(_reason_lines(analysis)),
                "리스크:",
                _format_plain_list(_risk_lines(analysis)),
                f"confidence: {_format_confidence(_get_value(analysis, 'confidence', default='명시되지 않음'))}",
                _get_value(
                    analysis,
                    "not_investment_advice",
                    default="이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
                ),
                "",
            ]
        )

    return "\n".join(sections).strip() + "\n"


def _build_html_body(analyses: list[dict]) -> str:
    """Build the HTML email body."""

    video_sections = "\n".join(
        _build_html_analysis_section(index, analysis)
        for index, analysis in enumerate(analyses, start=1)
    )
    return f"""<!doctype html>
<html lang="ko">
  <body>
    <h1>YouTube 새 영상 분석 결과</h1>
    <p><strong>주의:</strong> 이 메일은 투자 조언이 아니라 YouTube 영상 내용 요약입니다.</p>
    {video_sections}
  </body>
</html>
"""


def _build_html_analysis_section(index: int, analysis: dict) -> str:
    """Build one HTML section for one video analysis."""

    title = html.escape(_get_value(analysis, "video_title", "title"))
    url = _get_value(analysis, "video_url", "url")
    safe_url = html.escape(url, quote=True)
    visible_url = html.escape(url)
    summary = html.escape(_get_value(analysis, "summary"))
    basis_label = html.escape(_analysis_basis_label(analysis))
    basis_notice = html.escape(_analysis_basis_notice(analysis))
    confidence = html.escape(
        _format_confidence(_get_value(analysis, "confidence", default="명시되지 않음"))
    )
    advice_notice = html.escape(
        _get_value(
            analysis,
            "not_investment_advice",
            default="이 내용은 투자 조언이 아니라 영상 내용 요약입니다.",
        )
    )

    return f"""
    <section>
      <h2>영상 {index}: {title}</h2>
      <p><strong>영상 URL:</strong> <a href="{safe_url}">{visible_url}</a></p>
      <p><strong>분석 기준:</strong> {basis_label}</p>
      <p>{basis_notice}</p>
      <p><strong>요약:</strong> {summary}</p>
      <h3>언급 종목</h3>
      {_format_html_list(_stock_lines(analysis), "명확히 언급된 종목 없음")}
      <h3>언급 섹터</h3>
      {_format_html_list(_sector_lines(analysis), "명확히 언급된 섹터 없음")}
      <h3>언급 이유</h3>
      {_format_html_list(_reason_lines(analysis))}
      <h3>리스크</h3>
      {_format_html_list(_risk_lines(analysis))}
      <p><strong>confidence:</strong> {confidence}</p>
      <p><strong>안내:</strong> {advice_notice}</p>
    </section>
    <hr>
"""


def _stock_lines(analysis: dict) -> list[str]:
    """Return readable stock lines from an analysis dictionary."""

    recommended = _ensure_list(analysis.get("recommended_stocks"))
    watchlist = _ensure_list(analysis.get("watchlist_stocks"))
    lines = [
        _format_stock_item(item, "추천 언급") for item in recommended if isinstance(item, dict)
    ]
    lines.extend(
        _format_stock_item(item, "관심 언급") for item in watchlist if isinstance(item, dict)
    )
    return [line for line in lines if line]


def _sector_lines(analysis: dict) -> list[str]:
    """Return readable sector lines from an analysis dictionary."""

    sectors = _ensure_list(analysis.get("sectors"))
    return [
        _join_non_empty(
            [
                _string_value(item.get("name")),
                _string_value(item.get("reason")),
                _prefix_if_present("근거", _string_value(item.get("evidence"))),
            ],
            separator=" - ",
        )
        for item in sectors
        if isinstance(item, dict)
    ]


def _reason_lines(analysis: dict) -> list[str]:
    """Return reason lines from stocks and sectors."""

    lines: list[str] = []
    for key in ("recommended_stocks", "watchlist_stocks", "sectors"):
        for item in _ensure_list(analysis.get(key)):
            if not isinstance(item, dict):
                continue
            name = _string_value(item.get("name")) or "이름 없음"
            reason = _string_value(item.get("reason"))
            evidence = _string_value(item.get("evidence"))
            if reason or evidence:
                lines.append(
                    _join_non_empty(
                        [name, reason, _prefix_if_present("근거", evidence)],
                        separator=" - ",
                    )
                )
    return lines


def _risk_lines(analysis: dict) -> list[str]:
    """Return risk or uncertainty lines from an analysis dictionary."""

    risks = _ensure_list(analysis.get("risks") or analysis.get("risk"))
    uncertain_items = _ensure_list(analysis.get("uncertain_items"))
    source_limitations = _string_value(analysis.get("source_limitations"))

    lines = [_string_value(item) for item in risks if _string_value(item)]
    lines.extend(
        f"불확실한 항목: {_string_value(item)}"
        for item in uncertain_items
        if _string_value(item)
    )
    if source_limitations:
        lines.append(f"자료 한계: {source_limitations}")

    return lines


def _format_stock_item(item: dict, label: str) -> str:
    """Format one stock dictionary for email display."""

    name = _string_value(item.get("name")) or "이름 없음"
    ticker = _string_value(item.get("ticker"))
    reason = _string_value(item.get("reason"))
    evidence = _string_value(item.get("evidence"))

    stock_name = f"{name} ({ticker})" if ticker else name
    return _join_non_empty(
        [f"{label}: {stock_name}", reason, _prefix_if_present("근거", evidence)],
        separator=" - ",
    )


def _format_plain_list(
    items: list[str],
    empty_message: str = "명확히 언급되지 않음",
) -> str:
    """Format a list for plain text email."""

    if not items:
        return f"- {empty_message}"
    return "\n".join(f"- {item}" for item in items)


def _format_html_list(
    items: list[str],
    empty_message: str = "명확히 언급되지 않음",
) -> str:
    """Format a list for HTML email."""

    if not items:
        return f"<ul><li>{html.escape(empty_message)}</li></ul>"
    escaped_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{escaped_items}</ul>"


def _analysis_basis_label(analysis: dict) -> str:
    """Return a Korean label for the analysis basis."""

    basis = _string_value(analysis.get("analysis_basis"))
    labels = {
        "transcript": "자막 기반",
        "gemini_youtube_url": "Gemini YouTube URL 직접 분석",
        "metadata_plus_comments": "제목/설명/태그/댓글 기반 제한 분석",
        "metadata_only": "제목/설명/태그 기반 제한 분석",
    }
    return labels.get(basis, "분석 기준 미확인")


def _analysis_basis_notice(analysis: dict) -> str:
    """Return a user-facing notice for the analysis basis."""

    basis = _string_value(analysis.get("analysis_basis"))
    if basis == "gemini_youtube_url":
        return "자막 수집은 실패했지만 Gemini가 영상 URL을 직접 분석했습니다."
    if basis == "metadata_plus_comments":
        return (
            "영상 본문 직접 분석은 실패했고, 제목/설명/태그/댓글을 활용한 제한 분석입니다. "
            "댓글은 영상 발언이 아니라 보조 단서입니다."
        )
    if basis == "metadata_only":
        return "영상 본문 직접 분석과 댓글 분석이 실패해 제목/설명/태그만 기반으로 한 제한 분석입니다."
    if basis == "transcript":
        return "YouTube 자막/대본을 기반으로 분석했습니다."
    return "분석 기준 정보가 없습니다."


def _format_confidence(confidence: str) -> str:
    """Highlight low confidence."""

    return "LOW - 주의 필요" if confidence.lower() == "low" else confidence


def _get_value(analysis: dict, *keys: str, default: str = "명확히 언급되지 않음") -> str:
    """Return the first non-empty string value for the given keys."""

    for key in keys:
        value = _string_value(analysis.get(key))
        if value:
            return value
    return default


def _ensure_list(value: Any) -> list[Any]:
    """Return value as list when possible."""

    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


def _string_value(value: Any) -> str:
    """Return a stripped string or an empty string."""

    return value.strip() if isinstance(value, str) else ""


def _prefix_if_present(prefix: str, value: str) -> str:
    """Add a label prefix if value is present."""

    return f"{prefix}: {value}" if value else ""


def _join_non_empty(values: list[str], separator: str) -> str:
    """Join non-empty strings."""

    return separator.join(value for value in values if value)
