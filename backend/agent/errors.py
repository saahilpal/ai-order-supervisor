"""
Structured LLM error hierarchy.

Every error carries:
  user_message  — safe, actionable text for display (never a raw stack trace)
  error_code    — machine-readable category for programmatic handling
  original_error — the underlying exception for internal logging
"""

from __future__ import annotations
from typing import Optional


class LLMError(Exception):
    """Base class for all LLM provider errors."""

    error_code: str = "llm_error"

    def __init__(
        self,
        message: str,
        *,
        user_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or message
        self.original_error = original_error

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "user_message": self.user_message,
        }


class LLMConnectionError(LLMError):
    """Provider server is unreachable."""
    error_code = "llm_connection_error"


class LLMModelNotFoundError(LLMError):
    """Requested model does not exist on the provider."""
    error_code = "llm_model_not_found"


class LLMAuthenticationError(LLMError):
    """Missing or invalid API key / credentials."""
    error_code = "llm_authentication_error"


class LLMRateLimitError(LLMError):
    """Provider rate limit exceeded."""
    error_code = "llm_rate_limit"


class LLMContextWindowError(LLMError):
    """Prompt exceeds the model's context window."""
    error_code = "llm_context_window_exceeded"


class LLMTimeoutError(LLMError):
    """Provider did not respond within the configured timeout."""
    error_code = "llm_timeout"


class LLMProviderUnavailableError(LLMError):
    """Provider is temporarily unavailable (5xx, service outage)."""
    error_code = "llm_provider_unavailable"


class LLMConfigurationError(LLMError):
    """Invalid provider name, missing required env vars, or bad config."""
    error_code = "llm_configuration_error"
