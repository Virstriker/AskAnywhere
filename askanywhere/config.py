from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class Settings:
    gemini_api_key: str
    gemini_model: str


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    return Settings(gemini_api_key=api_key, gemini_model=model)
