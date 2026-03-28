from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


@dataclass
class ModelConfig:
    model_name: str  # e.g. "gemini/Gemini 3 Flash"  — provider is the prefix before /
    model_id: str    # e.g. "gemini-3-flash-preview"

    @property
    def provider(self) -> str:
        return self.model_name.split("/")[0].lower().strip()

    @property
    def display_name(self) -> str:
        parts = self.model_name.split("/", 1)
        return parts[1].strip() if len(parts) > 1 else self.model_name


@dataclass
class Settings:
    api_keys: dict        # {"gemini": "...", "openrouter": "..."}
    models: list          # list[ModelConfig]
    active_model: str     # model_id of the currently selected model

    def get_active_model(self) -> "ModelConfig | None":
        for m in self.models:
            if m.model_id == self.active_model:
                return m
        return self.models[0] if self.models else None

    def get_api_key(self, provider: str) -> str:
        return self.api_keys.get(provider.lower().strip(), "")


# ── helpers ────────────────────────────────────────────────────────────────

def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _parse_models(models_raw: list) -> list:
    return [
        ModelConfig(
            model_name=str(m.get("model_name", "")).strip(),
            model_id=str(m.get("model_id", "")).strip(),
        )
        for m in models_raw
        if m.get("model_name") and m.get("model_id")
    ]


def _load_json_settings(config_path: Path) -> Settings:
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    # ── API keys ──
    api_keys_raw = raw.get("api_keys", {})
    # backward compat: old flat "gemini_api_key" field
    if not api_keys_raw and raw.get("gemini_api_key"):
        api_keys_raw = {"gemini": raw["gemini_api_key"]}
    api_keys = {k.lower(): str(v).strip() for k, v in api_keys_raw.items()}

    # ── Models ──
    models_raw = raw.get("models", [])
    if not models_raw:
        # backward compat: old flat "gemini_model" field
        old_id = raw.get("gemini_model", "gemini-2.5-flash")
        models_raw = [{"model_name": f"gemini/{old_id}", "model_id": old_id}]
    models = _parse_models(models_raw)
    if not models:
        models = [ModelConfig("gemini/Gemini 2.5 Flash", "gemini-2.5-flash")]

    # ── Active model ──
    active_model = str(raw.get("active_model", models[0].model_id)).strip()
    # Validate: fall back to first if active_model not in list
    if not any(m.model_id == active_model for m in models):
        active_model = models[0].model_id

    return Settings(api_keys=api_keys, models=models, active_model=active_model)


def save_active_model(model_id: str) -> None:
    """Persist the chosen active model back to askanywhere.config.json."""
    config_path = _runtime_dir() / "askanywhere.config.json"
    if not config_path.exists():
        return
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw["active_model"] = model_id
        config_path.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as ex:
        print(f"[AskAnywhere][Config] Failed to save active model: {ex}", flush=True)


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

    # Dev mode — fall back to .env
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    return Settings(
        api_keys={"gemini": api_key},
        models=[ModelConfig(f"gemini/{model_id}", model_id)],
        active_model=model_id,
    )
