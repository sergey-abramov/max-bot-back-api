import json
import time
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, ensure_ascii=True))
