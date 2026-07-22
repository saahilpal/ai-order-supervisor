# LLM Provider Reference

The Order Supervisor communicates with all language models through a single `LLMProvider` interface defined in `backend/agent/provider.py`. Switching providers requires **only environment variable changes** — no workflow, activity, or business logic is modified.

---

## Quick Configuration

Set these environment variables before starting the backend:

```bash
# Google Gemini (default — no extra install needed)
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-2.5-pro
export GEMINI_API_KEY=your-key

# OpenAI
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export OPENAI_API_KEY=sk-...

# Ollama (local, no API key required)
export LLM_PROVIDER=ollama
export LLM_MODEL=llama3.1:8b

# Groq (fast inference)
export LLM_PROVIDER=groq
export LLM_MODEL=llama-3.3-70b-versatile
export GROQ_API_KEY=gsk_...
```

---

## Supported Providers

| Provider | `LLM_PROVIDER` | API Key Env | Default Model | Extra Install |
| :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** *(default)* | `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` | — |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | `pip install openai` |
| **Anthropic Claude** | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-haiku-latest` | `pip install anthropic` |
| **Azure OpenAI** | `azure` | `AZURE_OPENAI_API_KEY` | `gpt-4o` | `pip install openai` |
| **AWS Bedrock** | `bedrock` | AWS credentials | `claude-3-5-haiku` (Bedrock ID) | `pip install boto3` |
| **Groq** | `groq` | `GROQ_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **Together AI** | `together` | `TOGETHER_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **OpenRouter** | `openrouter` | `OPENROUTER_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **Mistral AI** | `mistral` | `MISTRAL_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` | `pip install openai` |
| **xAI (Grok)** | `xai` | `XAI_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **Hugging Face** | `huggingface` | `HUGGINGFACE_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |
| **Cohere** | `cohere` | `COHERE_API_KEY` | `command-r-plus-08-2024` | `pip install cohere` |
| **Ollama** *(local)* | `ollama` | — | *(set `LLM_MODEL`)* | Ollama running locally |
| **LM Studio** *(local)* | `lmstudio` | — | *(set `LLM_MODEL`)* | LM Studio server running |
| **vLLM** *(self-hosted)* | `vllm` | — | *(set `LLM_MODEL`)* | vLLM server running |
| **llama.cpp** *(local)* | `llamacpp` | — | *(set `LLM_MODEL`)* | llama.cpp server running |
| **LocalAI** *(local)* | `localai` | — | *(set `LLM_MODEL`)* | LocalAI server running |
| **Generic OpenAI-compat** | `openai_compat` | `OPENAI_COMPAT_API_KEY` | *(set `LLM_MODEL`)* | `pip install openai` |

### Additional env vars for specific providers

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-02-01

# OpenRouter (optional branding headers)
OPENROUTER_SITE_URL=https://your-site.com
OPENROUTER_SITE_NAME=Order Supervisor

# Custom OpenAI-compatible server — override base URL for any provider
LLM_BASE_URL=http://my-server:8080/v1
```

---

## Architecture

```
Temporal Workflow
       │
       ▼
 Agent Runtime (agent/core.py)
       │
       ▼
 LLMProvider interface (agent/provider.py)
       │
 ┌─────┼──────────────────────────────────────────────────────────┐
 │     │         │         │          │         │                 │
 ▼     ▼         ▼         ▼          ▼         ▼                 ▼
Gemini OpenAI  Claude  Bedrock    Cohere    Ollama (local)   OpenRouter
       │                                    LM Studio          Groq
       └── (one OpenAICompatibleProvider class,              Together
            different base_url per provider)                 Mistral
                                                             DeepSeek
                                                             xAI
                                                             vLLM
                                                             llama.cpp
                                                             LocalAI
                                                             HuggingFace
                                                             Generic
```

**Implementation note:** 15 of the 19 providers reuse a single `OpenAICompatibleProvider` class — they differ only in `base_url`, `api_key`, and whether they support `response_format: json_object`. The remaining 4 (Gemini, Anthropic, Bedrock, Cohere) each use their own SDK but implement the same `generate_json` contract.

---

## Local / Offline Setup

Run the Order Supervisor with **no cloud dependencies** using Ollama:

```bash
# 1. Install Ollama: https://ollama.com
ollama pull llama3.1:8b

# 2. Configure the backend
export LLM_PROVIDER=ollama
export LLM_MODEL=llama3.1:8b

# 3. Start services normally
uvicorn api.main:app --port 8000
python worker/main.py
```

The same pattern works for LM Studio, vLLM, llama.cpp, and LocalAI — just set `LLM_PROVIDER` and optionally `LLM_BASE_URL` if the server runs on a non-default port.
