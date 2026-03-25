# max-bot-back-api

Backend на FastAPI под Vercel Functions для поиска патентов через API Роспатента.

## Что уже реализовано

- FastAPI приложение в `api/index.py`.
- Endpoint `POST /api/patents/search` + `OPTIONS` preflight.
- Валидация входного payload (query/page/pageSize/filters).
- CORS whitelist только для `ALLOWED_ORIGIN`.
- In-memory rate limiting (best-effort, serverless friendly).
- Auth через `Authorization: Bearer <ROSPATENT_API_KEY>` (ключ из env).
- Нормализация ответа upstream в единый frontend-friendly формат.
- Единый формат ошибок.
- Структурные JSON-логи (`requestId`, `durationMs`, `statusCode`, и т.д.).

## Структура

- `api/index.py` — Vercel entrypoint и API маршруты.
- `app/config.py` — env-конфигурация.
- `app/schemas.py` — pydantic-схемы.
- `app/rospatent.py` — auth/search клиент к Роспатенту.
- `app/rate_limit.py` — простой rate limiter.
- `app/errors.py` — единый формат ошибок.
- `app/logging_utils.py` — структурные логи.
- `requirements.txt` — зависимости.
- `vercel.json` — роутинг и runtime.

---

## Контракт Frontend ↔ Backend (MVP)

### Endpoint

`POST /api/patents/search`

### CORS / Preflight

- Методы: `POST, OPTIONS`
- Заголовки: `Content-Type, X-Request-Id`
- Origin: строго равен `ALLOWED_ORIGIN` (без `*`)

### Request JSON

```json
{
  "query": "нейросеть",
  "queryMode": "qn",
  "page": 1,
  "pageSize": 20,
  "sort": "relevance",
  "datasets": ["cis"],
  "includeFacets": 0
}
```

#### Поля

- `query: string` — обязательное, длина `2..300`
- `queryMode?: "q" | "qn"` — default `qn` (`q` для query language, `qn` для естественного языка)
- `page?: number` — default `1`, min `1`
- `pageSize?: number` — default `20`, min `1`, max `50`
- `filters?: object` — маппится в upstream `filter`
- `sort?: string` — маппится в upstream `sort`
- `datasets?: string[]` — маппится в upstream `datasets`
- `includeFacets?: 0 | 1` — маппится в upstream `include_facets`

### Response 200 JSON

```json
{
  "items": [
    {
      "id": "RU123456U1",
      "title": "Способ обработки сигналов",
      "publishedAt": "2024-06-10",
      "applicant": "ООО Пример",
      "status": "published",
      "snippet": "Краткое описание патента...",
      "url": "https://example.org/patent/RU123456U1"
    }
  ],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "total": 124,
    "hasNext": true
  },
  "meta": {
    "source": "rospatent",
    "requestId": "req_abc123def456",
    "cached": false
  }
}
```

### Единый формат ошибки

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests",
    "requestId": "req_123",
    "details": {}
  }
}
```

### Коды ошибок

- `400 BAD_REQUEST` — невалидный JSON/payload
- `401 UPSTREAM_AUTH_FAILED` — auth к Роспатенту не удался
- `403 FORBIDDEN_ORIGIN` — origin запрещен
- `429 RATE_LIMITED` — превышен лимит
- `502 UPSTREAM_BAD_RESPONSE` — неожиданный ответ upstream
- `503 UPSTREAM_UNAVAILABLE` — timeout/сеть/upstream недоступен
- `500 INTERNAL_ERROR` — внутренняя ошибка

---

## JWT стратегия

- API-ключ Роспатента хранится только на backend в env: `ROSPATENT_API_KEY`.
- Во frontend ключ не уходит.
- Backend всегда отправляет `Authorization: Bearer <ROSPATENT_API_KEY>`.
- При `401` от Роспатента backend возвращает `UPSTREAM_AUTH_FAILED`.

---

## Environment Variables (Vercel)

Обязательные:

- `ROSPATENT_API_KEY`
- `ALLOWED_ORIGIN`
- `RATE_LIMIT_PER_MIN` (например `60`)
- `REQUEST_TIMEOUT_MS` (например `7000`)

Опциональные:

- `ROSPATENT_BASE_URL` (default `https://searchplatform.rospatent.gov.ru/patsearch/v0.2`)

Для локальной разработки используй `.env` (на основе `.env.example`), но не коммить его.

---

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

Пример запроса:

```bash
curl -X POST "http://127.0.0.1:8000/api/patents/search" \
  -H "Content-Type: application/json" \
  -H "Origin: https://<your-gh-pages-origin>" \
  -d '{"query":"нейросеть","page":1,"pageSize":20}'
```

Healthcheck:

`GET /api/health`

---
## Локальный запуск в Docker

Поднимает backend в контейнере, подхватывая настройки из локального `.env` (на основе `.env.example`).

Перед запуском создайте `.env` и заполните как минимум `ROSPATENT_API_KEY` и `ALLOWED_ORIGIN`.

```bash
docker compose up --build
```

Проверка:

```bash
curl -X POST "http://127.0.0.1:8000/api/patents/search" \
  -H "Content-Type: application/json" \
  -H "Origin: https://<your-allowed-origin>" \
  -d '{"query":"нейросеть","page":1,"pageSize":20}'
```

---
## Локальная проверка без секретов (mock)

Чтобы протестировать backend до деплоя в Vercel без реального `ROSPATENT_API_KEY`, используйте mock-режим upstream.

Скрипт `scripts/inprocess_smoke_test.py` прогоняет основные сценарии *в памяти* (in-process), поэтому `uvicorn` поднимать не нужно:

```bash
python3 scripts/inprocess_smoke_test.py
```

В mock-режиме по умолчанию разрешенный `Origin`:

`http://localhost:3000`

---

## Деплой в Vercel

1. Подключить репозиторий в Vercel.
2. Убедиться, что `vercel.json` в корне.
3. Добавить env vars из секции выше.
4. Деплой по `main`.
5. Smoke test:
   - preflight `OPTIONS /api/patents/search`
   - рабочий `POST /api/patents/search`
   - проверка ошибок (`400`, `403`, `429`)

---
