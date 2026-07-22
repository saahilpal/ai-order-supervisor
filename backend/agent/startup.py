"""
Startup verification for the configured LLM provider.

Called once during FastAPI startup. Raises LLMConfigurationError with a
clear, actionable message if anything is wrong — the server will refuse
to start rather than silently failing on the first real request.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from agent.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMTimeoutError,
)

logger = logging.getLogger("order_supervisor.startup")

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

# Providers that have no useful ping endpoint (require SDK calls)
_SKIP_PING_PROVIDERS = {"bedrock", "cohere"}

# Providers that need a non-empty API key
_REQUIRES_API_KEY: dict[str, str] = {
    "openai":       "OPENAI_API_KEY",
    "anthropic":    "ANTHROPIC_API_KEY",
    "azure":        "AZURE_OPENAI_API_KEY",
    "groq":         "GROQ_API_KEY",
    "together":     "TOGETHER_API_KEY",
    "openrouter":   "OPENROUTER_API_KEY",
    "mistral":      "MISTRAL_API_KEY",
    "deepseek":     "DEEPSEEK_API_KEY",
    "xai":          "XAI_API_KEY",
    "huggingface":  "HUGGINGFACE_API_KEY",
    "cohere":       "COHERE_API_KEY",
    "gemini":       "GEMINI_API_KEY",
}


# ── Ollama ────────────────────────────────────────────────────────────────────

async def _verify_ollama(base_url: str, model: str) -> None:
    """
    1. Confirm Ollama server is reachable (GET /api/tags).
    2. Confirm the requested model is installed locally.
    3. Run a minimal test inference.
    """
    tags_url = base_url.rstrip("/") + "/api/tags"

    # Step 1 — server reachability
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(tags_url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        raise LLMConnectionError(
            f"Cannot reach Ollama at {base_url}",
            user_message=(
                f"Unable to connect to Ollama.\n\n"
                f"Expected:\n  {base_url}\n\n"
                f"Please start Ollama:\n\n"
                f"  ollama serve\n\n"
                f"Then restart the application."
            ),
        )
    except httpx.TimeoutException:
        raise LLMTimeoutError(
            f"Ollama at {base_url} timed out",
            user_message=(
                f"Ollama did not respond within 5 seconds.\n\n"
                f"Please verify that Ollama is running:\n\n"
                f"  ollama serve"
            ),
        )
    except Exception as exc:
        raise LLMConnectionError(
            f"Ollama health check failed: {exc}",
            user_message=f"Unable to connect to Ollama at {base_url}: {exc}",
            original_error=exc,
        )

    # Step 2 — model installed?
    installed = {m.get("name", "").split(":")[0] for m in data.get("models", [])}
    installed_full = {m.get("name", "") for m in data.get("models", [])}
    target = model.split(":")[0]

    if model not in installed_full and target not in installed:
        raise LLMModelNotFoundError(
            f"Ollama model '{model}' not found locally",
            user_message=(
                f'Model "{model}" was not found in Ollama.\n\n'
                f"Install it using:\n\n"
                f"  ollama pull {model}\n\n"
                f"Installed models: {', '.join(sorted(installed_full)) or '(none)'}"
            ),
        )

    # Step 3 — test inference
    generate_url = base_url.rstrip("/") + "/api/generate"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                generate_url,
                json={"model": model, "prompt": "Hello", "stream": False},
            )
            resp.raise_for_status()
    except Exception as exc:
        raise LLMProviderUnavailableError(  # noqa: F821  (imported below)
            f"Ollama test inference failed: {exc}",
            user_message=(
                f"Ollama is running but test inference failed for model '{model}'.\n\n"
                f"Try:\n\n  ollama run {model}\n\nand check for errors."
            ),
            original_error=exc,
        ) from exc


# ── Generic OpenAI-compatible ping ────────────────────────────────────────────

async def _ping_openai_compat(base_url: str, api_key: str, provider_name: str) -> None:
    """Send GET /models to any OpenAI-compatible server as a lightweight health check."""
    models_url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "not-required" else {}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 401:
                raise LLMAuthenticationError(
                    f"{provider_name}: 401 Unauthorized",
                    user_message=(
                        f"{provider_name.title()} returned 401 Unauthorized.\n\n"
                        f"Verify your API key is correct and set:\n\n"
                        f"  {_REQUIRES_API_KEY.get(provider_name, 'API_KEY')}=your_api_key"
                    ),
                )
            if resp.status_code >= 500:
                raise LLMProviderUnavailableError(  # noqa: F821
                    f"{provider_name}: server error {resp.status_code}",
                    user_message=(
                        f"The {provider_name} server returned {resp.status_code}.\n\n"
                        f"The provider may be temporarily unavailable. Try again later."
                    ),
                )
            # 404 on /models is OK — some providers don't expose the endpoint
    except (LLMAuthenticationError, LLMModelNotFoundError):
        raise
    except httpx.ConnectError:
        raise LLMConnectionError(
            f"Cannot reach {provider_name} at {base_url}",
            user_message=(
                f"Unable to connect to {provider_name}.\n\n"
                f"Please verify:\n"
                f"  • Internet connection\n"
                f"  • Provider availability at {base_url or '(default endpoint)'}"
            ),
        )
    except httpx.TimeoutException:
        raise LLMTimeoutError(
            f"{provider_name} ping timed out",
            user_message=(
                f"The {provider_name} provider did not respond within the timeout.\n\n"
                f"Please verify:\n"
                f"  • Internet connection\n"
                f"  • Provider availability\n"
                f"  • API credentials"
            ),
        )


# ── Main entry point ──────────────────────────────────────────────────────────

async def verify_provider() -> None:
    """
    Verify the configured LLM provider on application startup.
    Raises a descriptive LLMError if anything is wrong.
    Called from FastAPI's startup_event.
    """
    name = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
    model = os.getenv("LLM_MODEL", "")
    base_url = os.getenv("LLM_BASE_URL", "")

    logger.info(f"Verifying LLM provider: {name!r}, model: {model!r}")

    # ── Configuration guard: unknown provider ─────────────────────────────────
    valid_providers = [
        "gemini", "openai", "anthropic", "azure", "bedrock", "cohere",
        "groq", "together", "openrouter", "mistral", "deepseek", "xai",
        "huggingface", "ollama", "lmstudio", "vllm", "llamacpp", "localai",
        "openai_compat",
    ]
    if name not in valid_providers:
        raise LLMConfigurationError(
            f"Unknown LLM_PROVIDER='{name}'",
            user_message=(
                f'Unknown LLM provider: "{name}"\n\n'
                f"Supported providers:\n\n"
                + "\n".join(f"  - {p}" for p in valid_providers)
            ),
        )

    # ── Configuration guard: missing API key ──────────────────────────────────
    key_env = _REQUIRES_API_KEY.get(name)
    if key_env and not os.getenv(key_env):
        raise LLMConfigurationError(
            f"{name}: {key_env} not set",
            user_message=(
                f"{name.title()} provider selected but {key_env} is not configured.\n\n"
                f"Add the following environment variable:\n\n"
                f"  {key_env}=your_api_key"
            ),
        )

    # ── Skip providers with no useful startup ping ────────────────────────────
    if name in _SKIP_PING_PROVIDERS:
        logger.info(f"Provider '{name}' does not support startup ping — skipping verification.")
        return

    # ── Ollama: full 3-step verification ──────────────────────────────────────
    if name == "ollama":
        ollama_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
        ollama_model = model or os.getenv("LLM_MODEL", "gemma4:latest")
        await _verify_ollama(ollama_url, ollama_model)
        logger.info(f"Ollama OK — model '{ollama_model}' is ready.")
        return

    # ── Local OpenAI-compatible servers (LM Studio, vLLM, etc.) ──────────────
    local_defaults = {
        "lmstudio": "http://localhost:1234/v1",
        "vllm":     "http://localhost:8080/v1",
        "llamacpp": "http://localhost:8080/v1",
        "localai":  "http://localhost:8080/v1",
    }
    if name in local_defaults:
        url = base_url or local_defaults[name]
        await _ping_openai_compat(url, "not-required", name)
        logger.info(f"Local provider '{name}' is reachable at {url}.")
        return

    # ── Cloud OpenAI-compatible providers ────────────────────────────────────
    cloud_defaults = {
        "openai":     "https://api.openai.com/v1",
        "groq":       "https://api.groq.com/openai/v1",
        "together":   "https://api.together.xyz/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "mistral":    "https://api.mistral.ai/v1",
        "deepseek":   "https://api.deepseek.com/v1",
        "xai":        "https://api.x.ai/v1",
        "huggingface":"https://api-inference.huggingface.co/v1",
        "openai_compat": None,
    }
    if name in cloud_defaults:
        url = base_url or cloud_defaults.get(name, "")
        api_key = os.getenv(_REQUIRES_API_KEY.get(name, ""), "not-required")
        await _ping_openai_compat(url, api_key, name)
        logger.info(f"Cloud provider '{name}' is reachable.")
        return

    # Gemini and Azure: SDK-level auth; no lightweight HTTP ping available
    logger.info(f"Provider '{name}' does not support lightweight ping — assuming configured correctly.")
