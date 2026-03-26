from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


@dataclass
class Settings:
    gemini_api_key: str
    gemini_model: str


def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _load_json_settings(config_path: Path) -> Settings:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    api_key = str(raw.get("gemini_api_key", "")).strip()
    model = str(raw.get("gemini_model", "gemini-2.5-flash")).strip()
    return Settings(gemini_api_key=api_key, gemini_model=model)


def load_settings() -> Settings:
    runtime_dir = _runtime_dir()
    config_path = runtime_dir / "askanywhere.config.json"

    if config_path.exists():
        return _load_json_settings(config_path)

    if getattr(sys, "frozen", False):
        raise RuntimeError(
            f"Missing config file: {config_path}. "
            "Create askanywhere.config.json next to the executable."
        )

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    return Settings(gemini_api_key=api_key, gemini_model=model)
