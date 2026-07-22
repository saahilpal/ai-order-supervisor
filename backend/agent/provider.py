"""
LLM Provider abstraction for Order Supervisor.

Architecture
────────────
  LLMProvider (abstract base)
    ├── call()          ← public API: logging + timeout + error mapping
    └── generate_json() ← provider-specific implementation (override this)

Concrete providers
──────────────────
  GoogleGenAIProvider       google-genai SDK
  OpenAICompatibleProvider  openai SDK (covers ~14 providers via base_url)
  AnthropicProvider         anthropic SDK
  AWSBedrockProvider        boto3
  CohereProvider            cohere SDK

Configuration (environment variables)
──────────────────────────────────────
  LLM_PROVIDER   = ollama          # default for local dev
  LLM_MODEL      = llama3.1:8b
  LLM_BASE_URL   = http://localhost:11434   # overrides default base URL
  LLM_TIMEOUT    = 60              # seconds; default 60

Quick examples
──────────────
  LLM_PROVIDER=gemini   LLM_MODEL=gemini-2.5-pro  GEMINI_API_KEY=...
  LLM_PROVIDER=openai   LLM_MODEL=gpt-4o           OPENAI_API_KEY=sk-...
  LLM_PROVIDER=ollama   LLM_MODEL=llama3.1:8b      (no key needed)
  LLM_PROVIDER=groq     LLM_MODEL=llama-3.3-70b    GROQ_API_KEY=gsk_...

See docs/LLM_PROVIDERS.md for a complete reference.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from agent.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMContextWindowError,
    LLMError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("order_supervisor.llm")


# ── Abstract base ─────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """
    Single contract every provider must implement.
    Callers use call() — never generate_json() directly.
    """

    # Subclasses should set these for logging
    provider_name: str = "unknown"
    model_name: str = "unknown"

    # ── Public API ────────────────────────────────────────────────────────────

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Any,
    ) -> Dict[str, Any]:
        """
        Call generate_json with:
          • configurable timeout (LLM_TIMEOUT env var, default 60s)
          • structured logging (provider, model, duration, success/failure)
          • exception mapping → our LLMError hierarchy
          • never exposes raw stack traces to callers
        """
        timeout = float(os.getenv("LLM_TIMEOUT", "60"))
        start = time.monotonic()

        logger.info(
            "llm_request_start",
            extra={
                "provider": self.provider_name,
                "model": self.model_name,
            },
        )

        try:
            result = await asyncio.wait_for(
                self.generate_json(system_prompt, user_prompt, response_schema),
                timeout=timeout,
            )
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "llm_request_success",
                extra={
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "duration_ms": round(duration_ms, 1),
                },
            )
            return result

        except asyncio.TimeoutError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "llm_request_timeout",
                extra={
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "duration_ms": round(duration_ms, 1),
                    "timeout_seconds": timeout,
                },
            )
            raise LLMTimeoutError(
                f"{self.provider_name}: timed out after {timeout}s",
                user_message=(
                    "The LLM provider did not respond within the configured timeout.\n\n"
                    "Please verify:\n"
                    "  • Internet connection\n"
                    "  • Provider availability\n"
                    "  • API credentials"
                ),
                original_error=exc,
            ) from exc

        except LLMError as exc:
            # Already mapped — just log and re-raise
            duration_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "duration_ms": round(duration_ms, 1),
                    "error_code": exc.error_code,
                },
            )
            raise

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            mapped = self._map_exception(exc)
            logger.error(
                "llm_request_error",
                extra={
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "duration_ms": round(duration_ms, 1),
                    "error_code": mapped.error_code,
                    "original_error_type": type(exc).__name__,
                },
            )
            raise mapped from exc

    # ── Abstract method: providers implement this ─────────────────────────────

    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Any,
    ) -> Dict[str, Any]:
        """Provider-specific LLM call. Raises any exception — call() maps them."""

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _schema_hint(self, schema: Any) -> str:
        try:
            if hasattr(schema, "model_json_schema"):
                return json.dumps(schema.model_json_schema(), indent=2)
            if hasattr(schema, "schema"):
                return json.dumps(schema.schema(), indent=2)
        except Exception:
            pass
        return str(schema)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON from text that may include markdown fences or prose."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            end = -1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[1:end]).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
            raise

    def _map_exception(self, exc: Exception) -> LLMError:
        """Map a raw third-party exception to our LLMError hierarchy."""
        msg = str(exc).lower()

        # Authentication / key issues
        if any(k in msg for k in ("401", "unauthorized", "authentication", "api key", "api_key", "invalid key")):
            return LLMAuthenticationError(
                str(exc),
                user_message=(
                    f"{self.provider_name.title()} rejected the request: authentication failed.\n\n"
                    "Please verify your API key is correct and has not expired."
                ),
                original_error=exc,
            )

        # Rate limits
        if any(k in msg for k in ("429", "rate limit", "rate_limit", "too many requests", "quota")):
            return LLMRateLimitError(
                str(exc),
                user_message=(
                    "Rate limit exceeded.\n\n"
                    "Please wait before sending another request, or switch to a different configured provider."
                ),
                original_error=exc,
            )

        # Context window
        if any(k in msg for k in ("context", "too long", "token limit", "maximum context", "context_length")):
            return LLMContextWindowError(
                str(exc),
                user_message=(
                    "The conversation exceeded the model's context window.\n\n"
                    "The application will automatically summarize previous messages and retry."
                ),
                original_error=exc,
            )

        # Model not found
        if any(k in msg for k in ("model not found", "no such model", "404", "does not exist")):
            return LLMModelNotFoundError(
                str(exc),
                user_message=(
                    f'Model "{self.model_name}" was not found.\n\n'
                    f"If using Ollama, install it with:\n\n  ollama pull {self.model_name}"
                ),
                original_error=exc,
            )

        # Connection errors
        if any(k in msg for k in ("connection", "connect", "network", "unreachable", "refused", "cannot")):
            return LLMConnectionError(
                str(exc),
                user_message=(
                    f"Unable to connect to {self.provider_name}.\n\n"
                    "Please verify:\n"
                    "  • The provider server is running\n"
                    "  • Your internet connection is active"
                ),
                original_error=exc,
            )

        # Server errors (5xx)
        if any(k in msg for k in ("502", "503", "504", "500", "service unavailable", "server error")):
            return LLMProviderUnavailableError(
                str(exc),
                user_message=(
                    f"The {self.provider_name} provider is currently unavailable.\n\n"
                    "Please switch to another configured provider or try again later."
                ),
                original_error=exc,
            )

        # Generic fallback
        return LLMProviderUnavailableError(
            str(exc),
            user_message=(
                f"The {self.provider_name} provider returned an unexpected error.\n\n"
                "Please try again or switch to another provider."
            ),
            original_error=exc,
        )


# ── 1. Google Gemini ──────────────────────────────────────────────────────────

class GoogleGenAIProvider(LLMProvider):
    """
    Google Gemini via the official Google GenAI SDK.
    pip install google-genai
    Env: GEMINI_API_KEY
    """

    provider_name = "gemini"

    def __init__(self, model: Optional[str] = None):
        from google import genai  # type: ignore
        self.client = genai.Client()
        self.model_name = model or os.getenv("LLM_MODEL", "gemini-2.5-flash")

    async def generate_json(self, system_prompt: str, user_prompt: str, response_schema: Any) -> Dict[str, Any]:
        from google.genai import types  # type: ignore

        loop = asyncio.get_event_loop()

        def _call():
            return self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            f"System Context:\n{system_prompt}\n\nUser Prompt:\n{user_prompt}"
                        )],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.2,
                ),
            )

        response = await loop.run_in_executor(None, _call)
        return self._extract_json(response.text)


# ── 2. OpenAI-Compatible (covers ~14 providers) ───────────────────────────────

class OpenAICompatibleProvider(LLMProvider):
    """
    Generic OpenAI-compatible provider.
    pip install openai

    Covers: OpenAI · Azure · Groq · Together · OpenRouter · Mistral ·
            DeepSeek · xAI · Hugging Face · Ollama · LM Studio ·
            vLLM · llama.cpp · LocalAI · any custom server
    """

    def __init__(
        self,
        *,
        provider_name: str = "openai_compat",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "default",
        supports_json_mode: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        from openai import AsyncOpenAI  # type: ignore

        self.provider_name = provider_name
        self.client = AsyncOpenAI(
            api_key=api_key or "not-required",
            base_url=base_url,
            default_headers=extra_headers or {},
        )
        self.model_name = model
        self.supports_json_mode = supports_json_mode

    async def generate_json(self, system_prompt: str, user_prompt: str, response_schema: Any) -> Dict[str, Any]:
        schema_hint = self._schema_hint(response_schema)
        system = (
            f"{system_prompt}\n\n"
            f"Respond with a valid JSON object only — no prose, no markdown fences.\n"
            f"The JSON must conform to this schema:\n{schema_hint}"
        )
        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        return self._extract_json(response.choices[0].message.content or "{}")


# ── 3. Anthropic Claude ───────────────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude via the official Anthropic SDK.
    pip install anthropic
    Env: ANTHROPIC_API_KEY
    """

    provider_name = "anthropic"

    def __init__(self, model: Optional[str] = None):
        import anthropic  # type: ignore
        self.client = anthropic.AsyncAnthropic()
        self.model_name = model or os.getenv("LLM_MODEL", "claude-3-5-haiku-latest")

    async def generate_json(self, system_prompt: str, user_prompt: str, response_schema: Any) -> Dict[str, Any]:
        schema_hint = self._schema_hint(response_schema)
        system = (
            f"{system_prompt}\n\n"
            f"Respond with a valid JSON object only — no prose, no markdown fences.\n"
            f"Schema:\n{schema_hint}"
        )
        message = await self.client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return self._extract_json(message.content[0].text)


# ── 4. AWS Bedrock ────────────────────────────────────────────────────────────

class AWSBedrockProvider(LLMProvider):
    """
    AWS Bedrock — supports Claude, Llama, Mistral, and other Bedrock models.
    pip install boto3
    Env: AWS_ACCESS_KEY_ID · AWS_SECRET_ACCESS_KEY · AWS_DEFAULT_REGION
    """

    provider_name = "bedrock"

    def __init__(self, model: Optional[str] = None, region: Optional[str] = None):
        import boto3  # type: ignore
        self.region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.runtime = boto3.client("bedrock-runtime", region_name=self.region)
        self.model_name = model or os.getenv("LLM_MODEL", "anthropic.claude-3-5-haiku-20241022-v1:0")

    async def generate_json(self, system_prompt: str, user_prompt: str, response_schema: Any) -> Dict[str, Any]:
        schema_hint = self._schema_hint(response_schema)
        full_prompt = (
            f"System: {system_prompt}\n\n"
            f"Schema:\n{schema_hint}\n\n"
            f"Respond with valid JSON only.\n\n"
            f"User: {user_prompt}"
        )
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": full_prompt}],
        })
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.runtime.invoke_model(
                modelId=self.model_name,
                body=body,
                contentType="application/json",
                accept="application/json",
            ),
        )
        result = json.loads(response["body"].read())
        return self._extract_json(result["content"][0]["text"])


# ── 5. Cohere ─────────────────────────────────────────────────────────────────

class CohereProvider(LLMProvider):
    """
    Cohere Command family via the official Cohere SDK.
    pip install cohere
    Env: COHERE_API_KEY
    """

    provider_name = "cohere"

    def __init__(self, model: Optional[str] = None):
        import cohere  # type: ignore
        self.client = cohere.AsyncClientV2(api_key=os.getenv("COHERE_API_KEY", ""))
        self.model_name = model or os.getenv("LLM_MODEL", "command-r-plus-08-2024")

    async def generate_json(self, system_prompt: str, user_prompt: str, response_schema: Any) -> Dict[str, Any]:
        schema_hint = self._schema_hint(response_schema)
        system = (
            f"{system_prompt}\n\n"
            f"Respond with valid JSON only.\nSchema:\n{schema_hint}"
        )
        response = await self.client.chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        )
        return self._extract_json(response.message.content[0].text)


# ── Provider registry ─────────────────────────────────────────────────────────

# OpenAI-compatible providers: (default_base_url, supports_json_mode, api_key_env)
_OPENAI_COMPAT: Dict[str, tuple] = {
    "openai":       (None,                                              True,  "OPENAI_API_KEY"),
    "groq":         ("https://api.groq.com/openai/v1",                 True,  "GROQ_API_KEY"),
    "together":     ("https://api.together.xyz/v1",                    True,  "TOGETHER_API_KEY"),
    "openrouter":   ("https://openrouter.ai/api/v1",                   True,  "OPENROUTER_API_KEY"),
    "mistral":      ("https://api.mistral.ai/v1",                      True,  "MISTRAL_API_KEY"),
    "deepseek":     ("https://api.deepseek.com/v1",                    True,  "DEEPSEEK_API_KEY"),
    "xai":          ("https://api.x.ai/v1",                            True,  "XAI_API_KEY"),
    "huggingface":  ("https://api-inference.huggingface.co/v1",        False, "HUGGINGFACE_API_KEY"),
    "ollama":       ("http://localhost:11434/v1",                       True,  ""),
    "lmstudio":     ("http://localhost:1234/v1",                        False, ""),
    "vllm":         ("http://localhost:8080/v1",                        True,  ""),
    "llamacpp":     ("http://localhost:8080/v1",                        False, ""),
    "localai":      ("http://localhost:8080/v1",                        True,  ""),
    "openai_compat": (None,                                             False, "OPENAI_COMPAT_API_KEY"),
}


def get_llm_provider() -> LLMProvider:
    """
    Read LLM_PROVIDER from the environment (default: ollama) and return the
    matching LLMProvider instance.

    Optional overrides:
        LLM_MODEL      — model name
        LLM_BASE_URL   — override base URL for OpenAI-compatible providers
        LLM_TIMEOUT    — request timeout in seconds (default 60)
    """
    name = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
    model = os.getenv("LLM_MODEL") or None
    base_url_override = os.getenv("LLM_BASE_URL") or None

    # ── Proprietary SDK providers ─────────────────────────────────────────────
    if name == "gemini":
        return GoogleGenAIProvider(model=model)

    if name == "anthropic":
        return AnthropicProvider(model=model)

    if name == "bedrock":
        return AWSBedrockProvider(model=model)

    if name == "cohere":
        return CohereProvider(model=model)

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    if name == "azure":
        from openai import AsyncAzureOpenAI  # type: ignore

        azure_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_endpoint = base_url_override or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

        if not azure_endpoint:
            raise LLMConfigurationError(
                "Azure: AZURE_OPENAI_ENDPOINT not set",
                user_message=(
                    "Azure OpenAI provider selected but AZURE_OPENAI_ENDPOINT is not configured.\n\n"
                    "Add the following environment variables:\n\n"
                    "  AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com\n"
                    "  AZURE_OPENAI_API_KEY=your_api_key"
                ),
            )

        provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        provider.provider_name = "azure"
        provider.client = AsyncAzureOpenAI(
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_version,
        )
        provider.model_name = model or os.getenv("LLM_MODEL", "gpt-4o")
        provider.supports_json_mode = True
        return provider

    # ── OpenAI-compatible providers ───────────────────────────────────────────
    if name in _OPENAI_COMPAT:
        default_url, json_mode, key_env = _OPENAI_COMPAT[name]
        api_key = (os.getenv(key_env) if key_env else None) or "not-required"
        base_url = base_url_override or default_url

        # Ollama: default model if not set
        if name == "ollama" and not model:
            model = os.getenv("LLM_MODEL", "llama3.1:8b")

        extra_headers: Optional[Dict[str, str]] = None
        if name == "openrouter":
            extra_headers = {
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": os.getenv("OPENROUTER_SITE_NAME", "Order Supervisor"),
            }

        return OpenAICompatibleProvider(
            provider_name=name,
            api_key=api_key,
            base_url=base_url,
            model=model or "default",
            supports_json_mode=json_mode,
            extra_headers=extra_headers,
        )

    raise LLMConfigurationError(
        f"Unknown LLM_PROVIDER='{name}'",
        user_message=(
            f'Unknown LLM provider: "{name}"\n\n'
            f"Supported providers:\n\n"
            + "\n".join(
                f"  - {p}"
                for p in [
                    "ollama", "gemini", "openai", "anthropic", "groq", "openrouter",
                    "together", "lmstudio", "vllm", "llamacpp", "localai", "azure",
                    "bedrock", "huggingface", "cohere", "mistral", "deepseek", "xai",
                    "openai_compat",
                ]
            )
        ),
    )
