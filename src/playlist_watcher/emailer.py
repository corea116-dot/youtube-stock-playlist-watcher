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
TEST_MODE_NOTICE = "테스트 모드로 실행되었습니다. 이미 처리된 영상도 다시 분석했을 수 있습니다."
INVESTMENT_NOTICE = "이 내용은 영상 요약이며 투자 조언이 아닙니다."


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

    run_mode = _run_mode(analyses)
    sections = [
        "[YouTube 종목 분석] 새 영상 분석 결과",
        f"실행 모드: {run_mode}",
        "분석 기준: Gemini YouTube URL 직접 분석",
        f"안내: {INVESTMENT_NOTICE}",
    ]
    if _has_test_mode(analyses):
        sections.append(TEST_MODE_NOTICE)
    sections.append("")

    for index, analysis in enumerate(analyses, start=1):
        market_view = _market_view(analysis)
        sections.extend(
            [
                f"===== 영상 {index} =====",
                f"1. 영상 제목: {_get_value(analysis, 'video_title', 'title')}",
                f"2. 영상 URL: {_get_value(analysis, 'video_url', 'url')}",
                f"3. 한줄 요약: {_get_value(analysis, 'summary')}",
                "4. 시장 전체 관점",
                f"- 판단: {_sentiment_label(market_view.get('overall_tone', 'uncertain'))}",
                f"- 이유: {_string_value(market_view.get('reason')) or '명확히 언급되지 않음'}",
                "",
                "5. 언급 종목 표",
                _plain_table(
                    headers=["종목명", "티커", "시장", "판단", "이유", "리스크", "신뢰도"],
                    rows=[
                        [
                            _string_value(item.get("name")),
                            _string_value(item.get("ticker")),
                            _string_value(item.get("market")),
                            _sentiment_label(_string_value(item.get("sentiment"))),
                            _string_value(item.get("reason")),
                            _string_value(item.get("risk")),
                            _confidence_label(_string_value(item.get("confidence"))),
                        ]
                        for item in _dict_list(analysis.get("mentioned_stocks"))
                    ],
                    empty_message="명확히 언급된 종목 없음",
                ),
                "",
                "6. 언급 섹터 표",
                _plain_table(
                    headers=["섹터", "판단", "이유", "리스크", "신뢰도"],
                    rows=[
                        [
                            _string_value(item.get("name")),
                            _sentiment_label(_string_value(item.get("sentiment"))),
                            _string_value(item.get("reason")),
                            _string_value(item.get("risk")),
                            _confidence_label(_string_value(item.get("confidence"))),
                        ]
                        for item in _dict_list(analysis.get("mentioned_sectors"))
                    ],
                    empty_message="명확히 언급된 섹터 없음",
                ),
                "",
                "7. 핵심 포인트",
                _format_plain_list(_string_list(analysis.get("key_points"))),
                "8. 추적 관찰 포인트",
                _format_plain_list(_string_list(analysis.get("watch_points"))),
                "9. 주의 문구",
                _get_value(
                    analysis,
                    "disclaimer",
                    "not_investment_advice",
                    default="이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
                ),
                "",
            ]
        )

    return "\n".join(sections).strip() + "\n"


def _build_html_body(analyses: list[dict]) -> str:
    """Build the HTML email body."""

    run_mode = html.escape(_run_mode(analyses))
    test_mode_notice = (
        f'<p style="padding:10px;background:#fff3cd;border:1px solid #ffe69c;">{html.escape(TEST_MODE_NOTICE)}</p>'
        if _has_test_mode(analyses)
        else ""
    )
    video_sections = "\n".join(
        _build_html_analysis_section(index, analysis)
        for index, analysis in enumerate(analyses, start=1)
    )
    return f"""<!doctype html>
<html lang="ko">
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5;color:#222;">
    <h1>{html.escape(EMAIL_SUBJECT)}</h1>
    <ul>
      <li><strong>실행 모드:</strong> {run_mode}</li>
      <li><strong>분석 기준:</strong> Gemini YouTube URL 직접 분석</li>
      <li><strong>안내:</strong> {html.escape(INVESTMENT_NOTICE)}</li>
    </ul>
    {test_mode_notice}
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
    market_view = _market_view(analysis)
    market_tone = html.escape(_sentiment_label(_string_value(market_view.get("overall_tone"))))
    market_reason = html.escape(_string_value(market_view.get("reason")) or "명확히 언급되지 않음")
    disclaimer = html.escape(
        _get_value(
            analysis,
            "disclaimer",
            "not_investment_advice",
            default="이 내용은 영상에서 언급된 내용을 요약한 것이며 투자 조언이 아닙니다.",
        )
    )

    stock_rows = [
        [
            _string_value(item.get("name")),
            _string_value(item.get("ticker")),
            _string_value(item.get("market")),
            _sentiment_label(_string_value(item.get("sentiment"))),
            _string_value(item.get("reason")),
            _string_value(item.get("risk")),
            _confidence_label(_string_value(item.get("confidence"))),
        ]
        for item in _dict_list(analysis.get("mentioned_stocks"))
    ]
    sector_rows = [
        [
            _string_value(item.get("name")),
            _sentiment_label(_string_value(item.get("sentiment"))),
            _string_value(item.get("reason")),
            _string_value(item.get("risk")),
            _confidence_label(_string_value(item.get("confidence"))),
        ]
        for item in _dict_list(analysis.get("mentioned_sectors"))
    ]

    return f"""
    <section style="margin:24px 0;padding:16px;border:1px solid #ddd;border-radius:8px;">
      <h2>영상 {index}. {title}</h2>
      <p><strong>영상 URL:</strong> <a href="{safe_url}">{visible_url}</a></p>
      <h3>한줄 요약</h3>
      <p>{summary}</p>
      <h3>시장 전체 관점</h3>
      <table style="border-collapse:collapse;width:100%;margin-bottom:16px;">
        <tbody>
          <tr><th style="border:1px solid #ddd;padding:8px;background:#f6f8fa;text-align:left;width:120px;">판단</th><td style="border:1px solid #ddd;padding:8px;">{market_tone}</td></tr>
          <tr><th style="border:1px solid #ddd;padding:8px;background:#f6f8fa;text-align:left;">이유</th><td style="border:1px solid #ddd;padding:8px;">{market_reason}</td></tr>
        </tbody>
      </table>
      <h3>언급 종목</h3>
      {_html_table(["종목명", "티커", "시장", "판단", "이유", "리스크", "신뢰도"], stock_rows, "명확히 언급된 종목 없음")}
      <h3>언급 섹터</h3>
      {_html_table(["섹터", "판단", "이유", "리스크", "신뢰도"], sector_rows, "명확히 언급된 섹터 없음")}
      <h3>핵심 포인트</h3>
      {_html_list(_string_list(analysis.get("key_points")))}
      <h3>추적 관찰 포인트</h3>
      {_html_list(_string_list(analysis.get("watch_points")))}
      <h3>주의 문구</h3>
      <p>{disclaimer}</p>
    </section>
"""


def _plain_table(headers: list[str], rows: list[list[str]], empty_message: str) -> str:
    """Build a simple plain-text table."""

    if not rows:
        return f"- {empty_message}"
    lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
    for row in rows:
        cleaned = [cell if cell else "-" for cell in row]
        lines.append(" | ".join(cleaned))
    return "\n".join(lines)


def _html_table(headers: list[str], rows: list[list[str]], empty_message: str) -> str:
    """Build an HTML table."""

    if not rows:
        return f"<p>{html.escape(empty_message)}</p>"

    header_html = "".join(
        f'<th style="border:1px solid #ddd;padding:8px;background:#f6f8fa;text-align:left;">{html.escape(header)}</th>'
        for header in headers
    )
    row_html = []
    for row in rows:
        cells = "".join(
            f'<td style="border:1px solid #ddd;padding:8px;vertical-align:top;">{html.escape(cell or "-")}</td>'
            for cell in row
        )
        row_html.append(f"<tr>{cells}</tr>")
    return (
        '<table style="border-collapse:collapse;width:100%;margin-bottom:16px;">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table>"
    )


def _format_plain_list(items: list[str], empty_message: str = "명확히 언급되지 않음") -> str:
    """Format a list for plain text email."""

    if not items:
        return f"- {empty_message}"
    return "\n".join(f"- {item}" for item in items)


def _html_list(items: list[str], empty_message: str = "명확히 언급되지 않음") -> str:
    """Format a list for HTML email."""

    if not items:
        return f"<p>{html.escape(empty_message)}</p>"
    escaped_items = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{escaped_items}</ul>"


def _run_mode(analyses: list[dict]) -> str:
    """Return the run/test mode for the email header."""

    for analysis in analyses:
        mode = _string_value(analysis.get("test_mode"))
        if mode:
            return mode
    return "normal"


def _has_test_mode(analyses: list[dict]) -> bool:
    """Return whether this email was generated by a manual test mode."""

    return _run_mode(analyses) in {"today", "latest_one"}


def _market_view(analysis: dict) -> dict[str, Any]:
    """Return market_view dict safely."""

    value = analysis.get("market_view")
    return value if isinstance(value, dict) else {"overall_tone": "uncertain", "reason": ""}


def _dict_list(value: Any) -> list[dict]:
    """Return dict items from a list-like value."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    """Return stripped string items from a list-like value."""

    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _sentiment_label(sentiment: str) -> str:
    """Translate sentiment to a Korean label."""

    labels = {
        "positive": "긍정",
        "negative": "부정",
        "neutral": "중립",
        "mixed": "혼조",
        "uncertain": "불확실",
    }
    return labels.get(sentiment.lower(), "불확실")


def _confidence_label(confidence: str) -> str:
    """Translate confidence to a Korean label."""

    labels = {"high": "높음", "medium": "보통", "low": "낮음"}
    return labels.get(confidence.lower(), "낮음")


def _get_value(analysis: dict, *keys: str, default: str = "명확히 언급되지 않음") -> str:
    """Return the first non-empty string value for the given keys."""

    for key in keys:
        value = _string_value(analysis.get(key))
        if value:
            return value
    return default


def _string_value(value: Any) -> str:
    """Return a stripped string or an empty string."""

    return value.strip() if isinstance(value, str) else ""
