from data_sources.models import now_iso

_health: dict = {}


def update_health(source: str, status: str, latency_ms: float | None = None, error: str | None = None, data_kind: str | None = None, is_cached: bool = False) -> None:
    _health[source] = {
        "source": source,
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
        "data_kind": data_kind,
        "is_cached": is_cached,
        "checked_at": now_iso(),
    }


def get_health() -> list[dict]:
    return sorted(_health.values(), key=lambda x: x["source"])


def reset_health() -> None:
    _health.clear()