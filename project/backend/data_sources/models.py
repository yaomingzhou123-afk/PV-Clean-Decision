from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


DATA_KINDS = ("forecast", "historical", "user_input", "simulation")
STATUSES = ("ok", "cached", "error")


def make_record(
    source: str,
    data_type: str,
    data_kind: str,
    latitude: float,
    longitude: float,
    value,
    unit,
    valid_time,
    status: str = "ok",
    fetched_at: str | None = None,
    is_simulated: bool = False,
    is_cached: bool = False,
    error_message: str | None = None,
) -> dict:
    if data_kind not in DATA_KINDS:
        raise ValueError(f"未知数据类型 data_kind: {data_kind}")
    if status not in STATUSES:
        raise ValueError(f"未知状态 status: {status}")
    return {
        "source": source,
        "data_type": data_type,
        "data_kind": data_kind,
        "latitude": round(float(latitude), 4),
        "longitude": round(float(longitude), 4),
        "value": value,
        "unit": unit,
        "valid_time": valid_time,
        "fetched_at": fetched_at or now_iso(),
        "status": status,
        "is_simulated": is_simulated,
        "is_cached": is_cached,
        "error_message": error_message,
    }


def error_record(source: str, data_type: str, data_kind: str, latitude: float, longitude: float, error_message: str) -> dict:
    return make_record(
        source=source,
        data_type=data_type,
        data_kind=data_kind,
        latitude=latitude,
        longitude=longitude,
        value=None,
        unit=None,
        valid_time=None,
        status="error",
        is_simulated=False,
        is_cached=False,
        error_message=error_message,
    )


def simulation_record(source: str, data_type: str, latitude: float, longitude: float, value, unit, valid_time) -> dict:
    return make_record(
        source=source,
        data_type=data_type,
        data_kind="simulation",
        latitude=latitude,
        longitude=longitude,
        value=value,
        unit=unit,
        valid_time=valid_time,
        status="ok",
        is_simulated=True,
        is_cached=False,
    )