from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.errors import ApiError, to_error_response
from app.logging_utils import log_event, now_ms
from app.rate_limit import InMemoryRateLimiter
from app.rospatent import MockRospatentClient, RospatentClient, normalize_response
from app.schemas import SearchRequest

app = FastAPI(title="max-bot-back-api", version="0.1.0")


def _load_runtime() -> tuple[Settings, RospatentClient | MockRospatentClient, InMemoryRateLimiter]:
    settings = load_settings()
    rospatent_client: RospatentClient | MockRospatentClient
    if settings.local_mock_rospatent:
        rospatent_client = MockRospatentClient(settings)
    else:
        rospatent_client = RospatentClient(settings)

    return settings, rospatent_client, InMemoryRateLimiter(settings.rate_limit_per_min)


SETTINGS, ROSPATENT, RATE_LIMITER = _load_runtime()


def _request_id(req: Request) -> str:
    header_id = req.headers.get("x-request-id")
    return header_id.strip() if header_id else f"req_{uuid.uuid4().hex[:12]}"


def _cors_headers(origin: str | None) -> dict[str, str]:
    if origin and origin == SETTINGS.allowed_origin:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Request-Id",
            "Vary": "Origin",
        }
    return {}


def _verify_origin(origin: str | None) -> None:
    if origin != SETTINGS.allowed_origin:
        raise ApiError(
            403,
            "FORBIDDEN_ORIGIN",
            "Origin is not allowed",
            {"allowed_origin": SETTINGS.allowed_origin, "received_origin": origin},
        )


def _rate_key(req: Request, origin: str) -> str:
    forwarded = req.headers.get("x-forwarded-for", "").split(",")[0].strip()
    host = req.client.host if req.client else "unknown"
    ip = forwarded or host
    return f"{origin}:{ip}"


def _client_payload(body: SearchRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        body.query_mode: body.query,
        "limit": body.page_size,
        "offset": (body.page - 1) * body.page_size,
    }
    if body.filters:
        payload["filter"] = body.filters
    if body.sort:
        payload["sort"] = body.sort
    if body.datasets:
        payload["datasets"] = body.datasets
    if body.include_facets is not None:
        payload["include_facets"] = body.include_facets
    return payload


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.options("/api/patents/search")
async def patents_search_options(request: Request) -> Response:
    origin = request.headers.get("origin")
    if origin != SETTINGS.allowed_origin:
        return Response(status_code=403)
    return Response(status_code=204, headers=_cors_headers(origin))


@app.post("/api/patents/search")
async def patents_search(request: Request) -> JSONResponse:
    started_ms = now_ms()
    request_id = _request_id(request)
    origin = request.headers.get("origin")
    headers = _cors_headers(origin)

    try:
        _verify_origin(origin)

        rate_key = _rate_key(request, origin or "no-origin")
        if not RATE_LIMITER.allow(rate_key):
            raise ApiError(429, "RATE_LIMITED", "Too many requests")

        try:
            raw = await request.json()
        except Exception as exc:
            raise ApiError(400, "BAD_REQUEST", "Invalid JSON payload") from exc

        try:
            body = SearchRequest.model_validate(raw)
        except ValidationError as exc:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "Invalid payload",
                {"validation": exc.errors(include_url=False)},
            ) from exc

        upstream_payload = _client_payload(body)
        upstream_data, upstream_status = await ROSPATENT.search(request_id, upstream_payload)
        normalized = normalize_response(upstream_data, body.page, body.page_size, request_id)

        duration = now_ms() - started_ms
        log_event(
            "request_finished",
            requestId=request_id,
            endpoint="/api/patents/search",
            durationMs=duration,
            statusCode=200,
            upstreamStatus=upstream_status,
        )
        return JSONResponse(status_code=200, content=normalized, headers=headers)

    except ApiError as err:
        duration = now_ms() - started_ms
        log_event(
            "request_failed",
            requestId=request_id,
            endpoint="/api/patents/search",
            durationMs=duration,
            statusCode=err.status_code,
            errorCode=err.code,
        )
        return JSONResponse(
            status_code=err.status_code,
            content=to_error_response(request_id, err),
            headers=headers,
        )
    except Exception as err:
        duration = now_ms() - started_ms
        log_event(
            "request_failed",
            requestId=request_id,
            endpoint="/api/patents/search",
            durationMs=duration,
            statusCode=500,
            errorCode="INTERNAL_ERROR",
            message=str(err),
        )
        api_err = ApiError(500, "INTERNAL_ERROR", "Internal server error")
        return JSONResponse(
            status_code=500,
            content=to_error_response(request_id, api_err),
            headers=headers,
        )
