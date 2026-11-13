import json
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def load_config(path="config/default.json"):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def groq_credentials():
    # Explicit file only: never discover parent .env, process key, or pdf/.env.
    values = dotenv_values(ROOT / ".env") if (ROOT / ".env").exists() else {}
    key = (values.get("GROQ_API_KEY") or "").strip()
    if not key or key == "replace_locally":
        raise RuntimeError("Configure GROQ_API_KEY locally in the root .env; key unavailable")
    return key, values.get("GROQ_MODEL") or "openai/gpt-oss-20b"
