import json
import os
from typing import Optional

_OVERRIDE_ENABLED: Optional[bool] = None


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled via environment variable or features.json."""
    global _OVERRIDE_ENABLED
    if _OVERRIDE_ENABLED is not None:
        return _OVERRIDE_ENABLED

    env_val = os.getenv("AUTOLOOP_FEATURES")
    if env_val is not None:
        if env_val.strip().lower() in ("0", "false", "no", "off", "disabled"):
            return False
        if env_val.strip().lower() in ("1", "true", "yes", "on", "enabled"):
            return True

    # Check features.json in CWD or telemetry directory
    for filepath in ("features.json", os.path.join("telemetry", "features.json")):
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        telemetry_cfg = data.get("telemetry")
                        if isinstance(telemetry_cfg, dict) and "enabled" in telemetry_cfg:
                            return bool(telemetry_cfg["enabled"])
                        if "telemetry.enabled" in data:
                            return bool(data["telemetry.enabled"])
            except Exception:
                pass

    return True


def set_telemetry_enabled(enabled: Optional[bool]) -> None:
    """Set explicit override for telemetry enabled state (useful for testing)."""
    global _OVERRIDE_ENABLED
    _OVERRIDE_ENABLED = enabled


from telemetry.config import *
