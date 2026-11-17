"""
AI settings, stored in config/api_config.json under the "ai" key.

config/api_config.json is git-ignored, so API keys stay on the machine.
Environment variables, if set, fill in anything the file leaves blank:
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, ANTHROPIC_API_KEY.
"""
import json
import os
from pathlib import Path

_CONFIG = Path(__file__).parent.parent.parent / "config" / "api_config.json"

# Models the admin can pick for the chat assistant (cheapest first).
CHAT_MODELS = [
    ("azure:gpt-5-4-mini", "GPT-5.4 mini (Azure) — recommended, cheapest"),
    ("claude-haiku-5-5",   "Claude Haiku 5.5 — cheap, needs Anthropic key"),
    ("claude-sonnet-5-5",  "Claude Sonnet 5.5 — needs Anthropic key"),
    ("azure:gpt-5-5",      "GPT-5.5 (Azure) — expensive"),
    ("claude-opus-5-5",    "Claude Opus 5.5 — expensive, needs Anthropic key"),
]

# Models for reading PDF / image drawings (best first). Counting columns on a
# dense plan needs the stronger model: on the Law College test GPT-5.5 matched
# the manual count exactly (C1 21, C4 28) where mini was off by one, at about
# $0.60 per page instead of $0.09.
DRAWING_MODELS = [
    ("azure:gpt-5-5",      "GPT-5.5 (Azure) — recommended, most accurate (~₹50 per page)"),
    ("azure:gpt-5-4-mini", "GPT-5.4 mini (Azure) — cheaper, counts can be off by a few"),
    ("claude-opus-5-5",    "Claude Opus 5.5 — needs Anthropic key"),
    ("claude-sonnet-5-5",  "Claude Sonnet 5.5 — needs Anthropic key"),
]

DEFAULTS = {
    "enabled": False,
    "chat_model": "azure:gpt-5-4-mini",
    "drawing_model": "azure:gpt-5-5",
    "azure_endpoint": "",
    "azure_api_key": "",
    "anthropic_api_key": "",
}


def _read_all() -> dict:
    try:
        return json.loads(_CONFIG.read_text())
    except Exception:
        return {}


def load() -> dict:
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (_read_all().get("ai") or {}).items() if k in DEFAULTS})
    s["azure_endpoint"] = s["azure_endpoint"] or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    s["azure_api_key"] = s["azure_api_key"] or os.environ.get("AZURE_OPENAI_API_KEY", "")
    s["anthropic_api_key"] = s["anthropic_api_key"] or os.environ.get("ANTHROPIC_API_KEY", "")
    return s


def save(settings: dict):
    """Write the "ai" section, keeping every other key in the file."""
    data = _read_all()
    data["ai"] = {k: settings.get(k, DEFAULTS[k]) for k in DEFAULTS}
    _CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG.write_text(json.dumps(data, indent=2))


def missing_credentials(s: dict) -> str:
    """Empty string if both chosen models can be called, else what is missing."""
    for key in ("chat_model", "drawing_model"):
        why = _missing_for(s.get(key, ""), s)
        if why:
            return why
    return ""


def _missing_for(m: str, s: dict) -> str:
    if m.startswith("azure:"):
        if not s.get("azure_endpoint") or not s.get("azure_api_key"):
            return "Azure endpoint / key not set"
    elif m.startswith("claude-"):
        if not s.get("anthropic_api_key"):
            return "Anthropic API key not set"
    else:
        return f"unknown model '{m}'"
    return ""
