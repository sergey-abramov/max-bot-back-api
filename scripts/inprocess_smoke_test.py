import asyncio
import importlib
import os
import sys
from typing import Any

import httpx


DEFAULT_ORIGIN = "http://localhost:3000"


def load_app(*, rate_limit_per_min: int) -> Any:
    """
    Перезагружает `api.index`, чтобы rate limiter и настройки применились заново.
    Это позволяет тестировать разные сценарии (в т.ч. rate limiting) в одном запуске.
    """

    os.environ["LOCAL_MOCK_ROSPATENT"] = "1"
    os.environ["ALLOWED_ORIGIN"] = os.environ.get("ALLOWED_ORIGIN", DEFAULT_ORIGIN)
    os.environ["RATE_LIMIT_PER_MIN"] = str(rate_limit_per_min)
    os.environ["REQUEST_TIMEOUT_MS"] = os.environ.get("REQUEST_TIMEOUT_MS", "1000")
    os.environ["ROSPATENT_BASE_URL"] = os.environ.get(
        "ROSPATENT_BASE_URL", "https://searchplatform.rospatent.gov.ru/patsearch/v0.2"
    )
    # При LOCAL_MOCK_ROSPATENT=1 ключ не обязателен, но пусть будет.
    os.environ["ROSPATENT_API_KEY"] = os.environ.get("ROSPATENT_API_KEY", "local-mock")

    if "api.index" in sys.modules:
        importlib.reload(sys.modules["api.index"])
    else:
        importlib.import_module("api.index")

    return sys.modules["api.index"].app


async def request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> Any:
    resp = await client.request(method, url, **kwargs)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


async def main() -> None:
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", DEFAULT_ORIGIN)
    valid_payload = {
        "query": "нейросеть",
        "queryMode": "qn",
        "page": 1,
        "pageSize": 3,
        "includeFacets": 0,
    }

    # 1) Базовые сценарии (без rate limit)
    app = load_app(rate_limit_per_min=60)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Healthcheck
        status, data = await request_json(client, "GET", "/api/health")
        if status != 200 or data.get("status") != "ok":
            raise AssertionError(f"Healthcheck failed: {status} {data}")

        # Preflight
        resp = await client.options(
            "/api/patents/search",
            headers={"origin": allowed_origin, "x-request-id": "req_preflight"},
        )
        if resp.status_code != 204:
            raise AssertionError(f"Preflight failed: {resp.status_code} {resp.text}")
        if resp.headers.get("access-control-allow-origin") != allowed_origin:
            raise AssertionError("Preflight missing/invalid CORS headers")

        # Forbidden origin
        status, data = await request_json(
            client,
            "POST",
            "/api/patents/search",
            headers={"origin": "http://evil.local", "x-request-id": "req_forbidden"},
            json=valid_payload,
        )
        if status != 403 or data.get("error", {}).get("code") != "FORBIDDEN_ORIGIN":
            raise AssertionError(f"Forbidden origin failed: {status} {data}")

        # Invalid payload (query too short)
        status, data = await request_json(
            client,
            "POST",
            "/api/patents/search",
            headers={"origin": allowed_origin, "x-request-id": "req_bad_payload"},
            json={**valid_payload, "query": "a"},
        )
        if status != 400 or data.get("error", {}).get("code") != "BAD_REQUEST":
            raise AssertionError(f"Invalid payload failed: {status} {data}")

        # Valid request
        status, data = await request_json(
            client,
            "POST",
            "/api/patents/search",
            headers={"origin": allowed_origin, "x-request-id": "req_ok"},
            json=valid_payload,
        )
        if status != 200:
            raise AssertionError(f"Valid request failed: {status} {data}")
        if not isinstance(data.get("items"), list):
            raise AssertionError("Valid request: missing `items` array")
        if "pagination" not in data or "meta" not in data:
            raise AssertionError("Valid request: missing `pagination`/`meta`")

    # 2) Rate limiting
    app = load_app(rate_limit_per_min=2)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(3):
            status, data = await request_json(
                client,
                "POST",
                "/api/patents/search",
                headers={"origin": allowed_origin, "x-request-id": f"req_rl_{i}"},
                json=valid_payload,
            )
            if i < 2 and status == 429:
                raise AssertionError("Rate limiter triggered too early")
            if i == 2:
                if status != 429 or data.get("error", {}).get("code") != "RATE_LIMITED":
                    raise AssertionError(f"Rate limiter failed: {status} {data}")

    print("inprocess_smoke_test: OK")


if __name__ == "__main__":
    asyncio.run(main())

