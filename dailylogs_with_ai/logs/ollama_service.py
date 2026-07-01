"""
logs/ollama_service.py
──────────────────────────────────────────────────────────────────────────────
Unified Ollama integration layer.

All LLM calls go through this module. It provides:
  - chat()        → multi-turn conversational responses (member & mentor bots)
  - generate_ai_report() → single-shot structured report generation

Requirements:
    pip install requests

Ollama must be running locally:
    ollama serve
    ollama pull llama3.2   (or whichever model you prefer)
"""

import requests
import json
import logging

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL    = "llama3.2:latest"   # change to "mistral:latest" etc. if preferred
CHAT_TIMEOUT    = 120   # seconds
REPORT_TIMEOUT  = 180   # reports can be longer


# ── Core helpers ──────────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict, timeout: int) -> dict:
    """
    Low-level POST to the Ollama HTTP API.
    Raises requests.HTTPError on non-2xx responses.
    """
    url = f"{OLLAMA_BASE_URL}{endpoint}"
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


# ── Public API ────────────────────────────────────────────────────────────────

def chat(messages: list[dict]) -> str:
    """
    Send a list of OpenAI-style message dicts to Ollama /api/chat and
    return the assistant reply string.

    messages format:
        [
            {"role": "system",    "content": "..."},
            {"role": "user",      "content": "..."},
            {"role": "assistant", "content": "..."},   # optional history
            ...
        ]
    """
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": messages,
        "stream":   False,
        "options": {
            "temperature": 0.4,   # lower = more factual, less hallucination
            "top_p":       0.9,
        },
    }
    try:
        data = _post("/api/chat", payload, CHAT_TIMEOUT)
        return data["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot reach Ollama. Make sure `ollama serve` is running on port 11434."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama timed out. The model may be loading – retry in a moment.")
    except KeyError:
        logger.error("Unexpected Ollama response shape: %s", data)
        raise RuntimeError("Unexpected response from Ollama.")


def generate_ai_report(prompt_text: str) -> str:
    """
    Generate a single-shot structured report via Ollama /api/generate.
    Used by the AI Report module (api_report_generate view).
    """
    full_prompt = (
        "You are a professional report writer for a daily log tracking app.\n"
        "Generate a clear, structured progress report using ONLY the information below.\n"
        "Format the report with these exact sections using markdown:\n\n"
        "## 📊 Overview\n"
        "## ✅ Key Activities\n"
        "## 📅 Missing Days\n"
        "## 💡 Suggestions\n\n"
        "Keep each section concise and professional. "
        "Use bullet points for activities. "
        "Never invent data not present in the input.\n\n"
        f"--- INPUT ---\n{prompt_text}"
    )
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    try:
        data = _post("/api/generate", payload, REPORT_TIMEOUT)
        return data["response"].strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Cannot reach Ollama. Make sure `ollama serve` is running.")
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama timed out while generating the report.")
    except KeyError:
        raise RuntimeError("Unexpected response from Ollama.")