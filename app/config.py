import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    rospatent_base_url: str
    rospatent_api_key: str
    allowed_origin: str
    rate_limit_per_min: int
    request_timeout_ms: int
    local_mock_rospatent: bool


def load_settings() -> Settings:
    base = os.getenv("ROSPATENT_BASE_URL", "https://searchplatform.rospatent.gov.ru/patsearch/v0.2").strip()
    local_mock_rospatent = _parse_bool(os.getenv("LOCAL_MOCK_ROSPATENT"), default=False)

    # В mock-режиме ключ Роспатента и allowed origin не обязательно задавать.
    # Это нужно, чтобы можно было протестировать backend локально без секретов.
    if local_mock_rospatent:
        rospatent_api_key = os.getenv("ROSPATENT_API_KEY", "local-mock").strip() or "local-mock"
        allowed_origin = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000").strip() or "http://localhost:3000"
    else:
        rospatent_api_key = _required("ROSPATENT_API_KEY")
        allowed_origin = _required("ALLOWED_ORIGIN")

    return Settings(
        rospatent_base_url=base.rstrip("/"),
        rospatent_api_key=rospatent_api_key,
        allowed_origin=allowed_origin,
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "60")),
        request_timeout_ms=int(os.getenv("REQUEST_TIMEOUT_MS", "7000")),
        local_mock_rospatent=local_mock_rospatent,
    )
