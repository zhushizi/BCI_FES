from __future__ import annotations

from typing import Optional

from service.business.config.config_service import ConfigService


def load_countdown_minutes() -> Optional[float]:
    try:
        service = ConfigService()
        value = service.get("Countdown_time_minutes")
        return float(value) if value is not None else None
    except Exception:
        return None
