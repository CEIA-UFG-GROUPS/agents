"""Test configuration.

Force LLM_ENABLED=false for the whole suite so tests are deterministic and never
make real Gemini calls — regardless of the developer's local .env. Tests that
exercise the LLM path inject a fake `generate` and pass use_llm=True explicitly.
"""

import os

os.environ["LLM_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
