"""
Pipeline Settings Store
=======================
Persists runtime-mutable pipeline feature flags to config/pipeline_settings.json.
Changes made via the admin UI take effect immediately without a server restart
and survive restarts.

Priority order (highest wins):
  1. Value saved via save_settings() / the admin UI
  2. Environment variable (LLM_JUDGE_ENABLED / LLM_CACHE_ENABLED)
  3. Hardcoded default

Usage:
    from webapp.settings_store import get_settings, save_settings

    cfg = get_settings()
    cfg["llm_judge_enabled"]  # bool
    cfg["llm_cache_enabled"]  # bool

    save_settings(llm_judge_enabled=False, llm_cache_enabled=True)
"""
import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger("tprm.settings_store")

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config" / "pipeline_settings.json"
_LOCK = threading.Lock()

# ── Defaults (overridden by env vars, then by saved file) ────────────────────
_DEFAULTS: dict[str, object] = {
    "llm_judge_enabled": True,
    "llm_cache_enabled": False,
}


def _env_overrides() -> dict[str, object]:
    """Read env-var overrides (applied when no saved file exists or key is missing)."""
    out: dict[str, object] = {}
    v = os.getenv("LLM_JUDGE_ENABLED")
    if v is not None:
        out["llm_judge_enabled"] = v.lower() == "true"
    v = os.getenv("LLM_CACHE_ENABLED")
    if v is not None:
        out["llm_cache_enabled"] = v.lower() == "true"
    return out


def _load_file() -> dict:
    """Load the settings file, returning {} if missing or corrupt."""
    try:
        if _SETTINGS_FILE.exists():
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read pipeline_settings.json: %s", exc)
    return {}


def get_settings() -> dict[str, object]:
    """
    Return the current settings dict.
    Keys: llm_judge_enabled (bool), llm_cache_enabled (bool)
    """
    with _LOCK:
        base = {**_DEFAULTS, **_env_overrides(), **_load_file()}
    return base


def save_settings(**kwargs) -> dict[str, object]:
    """
    Persist one or more settings.  Unknown keys are ignored.

    Example:
        save_settings(llm_judge_enabled=False)
    """
    with _LOCK:
        current = {**_DEFAULTS, **_env_overrides(), **_load_file()}
        for key, value in kwargs.items():
            if key in _DEFAULTS:
                current[key] = bool(value)
            else:
                logger.warning("save_settings: unknown key %r ignored", key)

        try:
            _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_FILE.write_text(
                json.dumps(current, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Could not write pipeline_settings.json: %s", exc)
            raise

        # ── Propagate to live module-level vars so in-process code sees the change
        # immediately without a restart.
        _apply_to_live_modules(current)
        return current


def _apply_to_live_modules(settings: dict) -> None:
    """Update cached module-level constants in already-imported modules."""
    try:
        import webapp.config as _cfg
        _cfg.LLM_JUDGE_ENABLED = settings["llm_judge_enabled"]
        _cfg.LLM_CACHE_ENABLED = settings["llm_cache_enabled"]
    except Exception as exc:
        logger.debug("Could not patch webapp.config: %s", exc)

    try:
        import webapp.pipeline_runner as _pr
        _pr.LLM_JUDGE_ENABLED = settings["llm_judge_enabled"]
        _pr.LLM_CACHE_ENABLED = settings["llm_cache_enabled"]
    except Exception as exc:
        logger.debug("Could not patch pipeline_runner: %s", exc)
