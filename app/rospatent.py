from typing import Any

import httpx

from app.config import Settings
from app.errors import ApiError


class RospatentClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(self, request_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        timeout = self.settings.request_timeout_ms / 1000
        url = f"{self.settings.rospatent_base_url}/search"
        headers = {
            "Authorization": f"Bearer {self.settings.rospatent_api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", "Rospatent upstream timeout") from exc
        except httpx.HTTPError as exc:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", "Rospatent upstream unavailable") from exc

        if response.status_code == 401:
            raise ApiError(401, "UPSTREAM_AUTH_FAILED", "Invalid or expired Rospatent API key")

        if response.status_code >= 500:
            raise ApiError(
                503,
                "UPSTREAM_UNAVAILABLE",
                "Rospatent upstream unavailable",
                {"upstreamStatus": response.status_code},
            )
        if response.status_code >= 400:
            raise ApiError(
                502,
                "UPSTREAM_BAD_RESPONSE",
                "Unexpected upstream response",
                {"upstreamStatus": response.status_code},
            )

        data = response.json()
        return data, response.status_code


class MockRospatentClient:
    """
    Локальный mock-упрост для проверки backend без реальных внешних запросов.
    Возвращает данные в формате, который умеет нормализовать `normalize_response`.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(self, request_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        limit = int(payload.get("limit") or 20)
        offset = int(payload.get("offset") or 0)
        # Фиксированное общее количество: удобно проверять пагинацию.
        total = 37

        # payload от backend строится как {<query_mode>: <query>, limit, offset, ...}
        query = str(payload.get("qn") or payload.get("q") or "")

        hits: list[dict[str, Any]] = []
        for i in range(limit):
            idx = offset + i + 1
            if idx > total:
                break
            hits.append(
                {
                    "id": f"RU_MOCK_{idx}",
                    "biblio": {
                        "ru": {
                            "title": f"Тестовый патент: {query or 'demo'} #{idx}",
                            "applicant": [{"name": "ООО Тест"}],
                        }
                    },
                    "common": {"publication_date": "2024-06-10", "kind": "published", "application": {}},
                    "snippet": {"description": f"Описание по запросу '{query or 'demo'}' (mock) #{idx}", "applicant": None},
                    "meta": {"source": {"path": f"https://example.org/patent/RU_MOCK_{idx}"}},
                }
            )

        data = {"hits": hits, "total": total, "requestId": request_id}
        return data, 200


def normalize_response(data: dict[str, Any], page: int, page_size: int, request_id: str) -> dict[str, Any]:
    raw_items = data.get("hits") or data.get("items") or data.get("results") or []
    items = []

    for raw in raw_items:
        item_id = (
            raw.get("id")
            or raw.get("docId")
            or raw.get("documentId")
            or raw.get("publicationNumber")
            or ""
        )
        biblio = raw.get("biblio", {})
        biblio_ru = biblio.get("ru", {})
        title = biblio_ru.get("title") or raw.get("title") or "Untitled"
        common = raw.get("common", {})
        application = common.get("application", {})
        snippet_obj = raw.get("snippet", {})
        url = None
        source_path = raw.get("meta", {}).get("source", {}).get("path")
        if isinstance(source_path, str) and source_path:
            url = f"{source_path}"
        items.append(
            {
                "id": str(item_id),
                "title": str(title),
                "publishedAt": common.get("publication_date") or raw.get("publishedAt"),
                "applicant": (
                    snippet_obj.get("applicant")
                    or _join_names(biblio_ru.get("applicant"))
                    or raw.get("applicant")
                ),
                "status": common.get("kind") or raw.get("status"),
                "snippet": snippet_obj.get("description") or raw.get("snippet") or raw.get("abstract"),
                "url": raw.get("url") or raw.get("link") or url,
            }
        )

    total = int(data.get("total") or len(items))
    has_next = (page * page_size) < total

    return {
        "items": items,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": int(total),
            "hasNext": bool(has_next),
        },
        "meta": {"source": "rospatent", "requestId": request_id, "cached": False},
    }


def _join_names(raw_people: Any) -> str | None:
    if not isinstance(raw_people, list):
        return None
    names = [p.get("name") for p in raw_people if isinstance(p, dict) and p.get("name")]
    if not names:
        return None
    return ", ".join(str(name) for name in names)
