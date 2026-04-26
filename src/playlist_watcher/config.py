"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_MAX_VIDEOS_TO_CHECK = 5
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

REQUIRED_ENV_VARS = (
    "YOUTUBE_API_KEY",
    "OPENAI_API_KEY",
    "PLAYLIST_ID",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "EMAIL_TO",
)


class ConfigError(ValueError):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Settings needed by the application."""

    youtube_api_key: str
    openai_api_key: str
    playlist_id: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    email_to: str
    max_videos_to_check: int = DEFAULT_MAX_VIDEOS_TO_CHECK
    openai_model: str = DEFAULT_OPENAI_MODEL


def load_config(environ: Mapping[str, str] | None = None) -> AppConfig:
    """Load application settings from environment variables.

    Real API keys, passwords, and tokens must be provided by the environment
    or GitHub Secrets. They should never be hard-coded in this project.
    """

    env = environ if environ is not None else os.environ
    missing_names = [name for name in REQUIRED_ENV_VARS if not env.get(name)]

    if missing_names:
        formatted_names = ", ".join(missing_names)
        raise ConfigError(
            "필수 환경변수가 설정되지 않았습니다: "
            f"{formatted_names}\n"
            "초보자 안내: 로컬 테스트라면 .env 파일 또는 터미널 환경변수에 값을 넣고, "
            "GitHub Actions에서 실행한다면 GitHub Secrets에 같은 이름으로 등록해야 합니다. "
            "필요한 이름은 .env.example 파일을 참고하세요."
        )

    smtp_port = _parse_positive_int(env["SMTP_PORT"], "SMTP_PORT")
    raw_max_videos_to_check = env.get("MAX_VIDEOS_TO_CHECK") or str(
        DEFAULT_MAX_VIDEOS_TO_CHECK
    )
    max_videos_to_check = _parse_positive_int(
        raw_max_videos_to_check,
        "MAX_VIDEOS_TO_CHECK",
    )

    return AppConfig(
        youtube_api_key=env["YOUTUBE_API_KEY"],
        openai_api_key=env["OPENAI_API_KEY"],
        playlist_id=env["PLAYLIST_ID"],
        smtp_host=env["SMTP_HOST"],
        smtp_port=smtp_port,
        smtp_user=env["SMTP_USER"],
        smtp_pass=env["SMTP_PASS"],
        email_to=env["EMAIL_TO"],
        max_videos_to_check=max_videos_to_check,
        openai_model=env.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
    )


def _parse_positive_int(value: str, env_name: str) -> int:
    """Parse a positive integer from an environment variable value."""

    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise ConfigError(
            f"{env_name} 값은 숫자여야 합니다. 현재 값: {value!r}\n"
            "초보자 안내: 예를 들어 SMTP_PORT는 보통 465 또는 587 같은 숫자입니다."
        ) from exc

    if parsed_value <= 0:
        raise ConfigError(
            f"{env_name} 값은 1 이상의 숫자여야 합니다. 현재 값: {value!r}"
        )

    return parsed_value
