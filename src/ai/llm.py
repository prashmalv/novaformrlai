"""
Vision LLM providers behind one small interface.

A request is a list of neutral content parts:
    ("image", png_bytes) | ("text", str) | ("cache", None)
"cache" marks the end of the shared prefix (system + overview), which the
provider may cache. Only Anthropic is implemented in Phase 1; GPT / Gemini /
OpenAI-compatible adapters plug in by subclassing VisionLLM.
"""
import base64
import os
import time
from dataclasses import dataclass

# USD per 1M tokens (input, output). Cache reads/writes are priced by the
# provider; we keep the usage numbers so cost can be recomputed later.
PRICES = {
    "claude-opus-5-5":   (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5":  (0.10, 0.50),
    # Azure Data Zone (US) retail, eastus2, Nov 2026
    "azure:gpt-5-4-mini": (0.825, 4.95),
    "azure:gpt-5-5":      (5.50, 33.00),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    seconds: float = 0.0
    calls: int = 0

    def add(self, other: "Usage"):
        for f in ("input_tokens", "output_tokens", "cache_read", "cache_write", "seconds", "calls"):
            setattr(self, f, getattr(self, f) + getattr(other, f))

    def cost_usd(self, model: str) -> float:
        p_in, p_out = PRICES.get(model, (0.0, 0.0))
        # Cache writes bill at 1.25x input, reads at 0.1x input.
        return round((self.input_tokens * p_in + self.cache_write * p_in * 1.25
                      + self.cache_read * p_in * 0.1 + self.output_tokens * p_out) / 1e6, 4)


class LLMError(RuntimeError):
    pass


class VisionLLM:
    model: str = ""

    def structured(self, system: str, parts: list, schema, max_tokens: int = 32000):
        """Return (parsed schema instance, Usage)."""
        raise NotImplementedError


class AnthropicVision(VisionLLM):
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", api_key: str = None):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def _content(self, parts: list) -> list:
        blocks = []
        for kind, value in parts:
            if kind == "image":
                blocks.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": base64.standard_b64encode(value).decode("ascii")}})
            elif kind == "text":
                blocks.append({"type": "text", "text": value})
            elif kind == "cache" and blocks:
                blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return blocks

    def structured(self, system: str, parts: list, schema, max_tokens: int = 32000):
        a = self._anthropic
        t0 = time.time()
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": self._content(parts)}],
                output_config={"effort": self.effort},
                output_format=schema,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                msg = stream.get_final_message()
        except a.AuthenticationError as e:
            raise LLMError("API key rejected - set ANTHROPIC_API_KEY") from e
        except a.BadRequestError as e:
            raise LLMError(f"Bad request: {e.message}") from e
        except a.RateLimitError as e:
            raise LLMError("Rate limited by the API, try again shortly") from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Cannot reach the API - check internet / proxy") from e

        if msg.stop_reason == "refusal":
            raise LLMError("Model declined the request")
        if msg.stop_reason == "max_tokens":
            raise LLMError("Answer cut off at max_tokens")
        if msg.parsed_output is None:
            raise LLMError("Model returned no structured output")

        u = msg.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
            seconds=time.time() - t0, calls=1)
        return msg.parsed_output, usage


class AzureOpenAIVision(VisionLLM):
    """GPT models deployed in Azure AI Foundry, via the OpenAI v1 endpoint.

    AZURE_OPENAI_ENDPOINT  e.g. https://nova-formwork-ai.openai.azure.com
    AZURE_OPENAI_API_KEY   key of that resource
    The model name is the Azure *deployment* name (e.g. gpt-5-5).
    Prompt caching is automatic on Azure for repeated prefixes >1024 tokens.
    """

    def __init__(self, deployment: str, effort: str = "high"):
        import openai
        self._openai = openai
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        key = os.environ.get("AZURE_OPENAI_API_KEY")
        if not endpoint or not key:
            raise LLMError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not set")
        self.client = openai.OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=key, max_retries=3)
        self.model = deployment
        # OpenAI reasoning effort has no 'max'/'xhigh' on every model; map down.
        self.effort = {"xhigh": "high", "max": "high"}.get(effort, effort)

    def _content(self, parts: list) -> list:
        blocks = []
        for kind, value in parts:
            if kind == "image":
                blocks.append({"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.standard_b64encode(value).decode("ascii"),
                    "detail": "high"}})
            elif kind == "text":
                blocks.append({"type": "text", "text": value})
        return blocks

    def structured(self, system: str, parts: list, schema, max_tokens: int = 32000):
        o = self._openai
        t0 = time.time()
        try:
            resp = self.client.chat.completions.parse(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": self._content(parts)}],
                response_format=schema,
                max_completion_tokens=max_tokens,
                reasoning_effort=self.effort,
            )
        except o.AuthenticationError as e:
            raise LLMError("Azure key rejected - check AZURE_OPENAI_API_KEY") from e
        except o.NotFoundError as e:
            raise LLMError(f"Deployment '{self.model}' not found on the Azure resource") from e
        except o.RateLimitError as e:
            raise LLMError("Azure rate limit (TPM quota) hit, try again shortly") from e
        except o.BadRequestError as e:
            raise LLMError(f"Bad request: {e.message}") from e
        except o.APIStatusError as e:
            raise LLMError(f"Azure error {e.status_code}: {e.message}") from e
        except o.APIConnectionError as e:
            raise LLMError("Cannot reach Azure - check internet / proxy") from e
        except o.LengthFinishReasonError as e:
            raise LLMError("Answer cut off at max_tokens") from e

        msg = resp.choices[0].message
        if msg.refusal:
            raise LLMError(f"Model declined: {msg.refusal}")
        if msg.parsed is None:
            raise LLMError("Model returned no structured output")
        u = resp.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        usage = Usage(input_tokens=(u.prompt_tokens or 0) - cached,
                      output_tokens=u.completion_tokens or 0,
                      cache_read=cached, seconds=time.time() - t0, calls=1)
        return msg.parsed, usage


def chat_text(model: str, system: str, messages: list, creds: dict,
              max_tokens: int = 2000) -> tuple:
    """Plain text chat for the BOQ assistant. messages: [{"role", "content"}].
    creds: azure_endpoint / azure_api_key / anthropic_api_key (src.ai.settings).
    Returns (answer text, Usage)."""
    t0 = time.time()
    if model.startswith("azure:"):
        import openai as o
        endpoint = (creds.get("azure_endpoint") or "").rstrip("/")
        client = o.OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=creds.get("azure_api_key"),
                          max_retries=2, timeout=90)
        try:
            resp = client.chat.completions.create(
                model=model.split(":", 1)[1],
                messages=[{"role": "system", "content": system}] + messages,
                max_completion_tokens=max_tokens, reasoning_effort="low")
        except o.AuthenticationError as e:
            raise LLMError("Azure key rejected - check AI Settings in Admin Panel") from e
        except o.NotFoundError as e:
            raise LLMError(f"Deployment '{model}' not found on the Azure resource") from e
        except o.RateLimitError as e:
            raise LLMError("Azure rate limit hit, try again shortly") from e
        except o.APIStatusError as e:
            raise LLMError(f"Azure error {e.status_code}: {e.message}") from e
        except o.APIConnectionError as e:
            raise LLMError("Cannot reach Azure - check internet / proxy") from e
        choice = resp.choices[0]
        u = resp.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        usage = Usage(input_tokens=(u.prompt_tokens or 0) - cached, output_tokens=u.completion_tokens or 0,
                      cache_read=cached, seconds=time.time() - t0, calls=1)
        text = choice.message.content or ""
        if choice.finish_reason == "length" and not text:
            raise LLMError("Answer cut off - ask a narrower question")
        return text, usage

    if model.startswith("claude-"):
        import anthropic as a
        client = a.Anthropic(api_key=creds.get("anthropic_api_key"), max_retries=2, timeout=90)
        try:
            msg = client.messages.create(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages)
        except a.AuthenticationError as e:
            raise LLMError("Anthropic key rejected - check AI Settings in Admin Panel") from e
        except a.RateLimitError as e:
            raise LLMError("Rate limited by the API, try again shortly") from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Cannot reach the API - check internet / proxy") from e
        if msg.stop_reason == "refusal":
            raise LLMError("Model declined the request")
        u = msg.usage
        usage = Usage(input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
                      cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
                      cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
                      seconds=time.time() - t0, calls=1)
        return "".join(b.text for b in msg.content if b.type == "text"), usage

    raise LLMError(f"No provider for model '{model}'")


def _image_block(provider: str, png: bytes) -> dict:
    b64 = base64.standard_b64encode(png).decode("ascii")
    if provider == "azure":
        return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64, "detail": "high"}}
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}


def chat_structured(model: str, system: str, messages: list, schema, creds: dict,
                    max_tokens: int = 8000, effort: str = "low") -> tuple:
    """Multi-turn chat whose last answer must match a Pydantic schema.
    messages: [{"role", "content"}]; content is a str, or a list of
    ("text", str) / ("image", png_bytes) parts for vision.
    Returns (parsed schema instance, Usage). Raises LLMError."""
    t0 = time.time()
    if model.startswith("azure:"):
        import openai as o
        def conv(c):
            if isinstance(c, str):
                return c
            return [{"type": "text", "text": v} if k == "text" else _image_block("azure", v) for k, v in c]
        endpoint = (creds.get("azure_endpoint") or "").rstrip("/")
        client = o.OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=creds.get("azure_api_key"),
                          max_retries=2, timeout=300)
        try:
            resp = client.chat.completions.parse(
                model=model.split(":", 1)[1],
                messages=[{"role": "system", "content": system}]
                         + [{"role": m["role"], "content": conv(m["content"])} for m in messages],
                response_format=schema, max_completion_tokens=max_tokens,
                reasoning_effort={"xhigh": "high", "max": "high"}.get(effort, effort))
        except o.AuthenticationError as e:
            raise LLMError("Azure key rejected - check AI Settings in Admin Panel") from e
        except o.NotFoundError as e:
            raise LLMError(f"Deployment '{model}' not found on the Azure resource") from e
        except o.RateLimitError as e:
            raise LLMError("Azure rate limit hit, try again shortly") from e
        except o.LengthFinishReasonError as e:
            raise LLMError("Answer too long - try a smaller request") from e
        except o.APIStatusError as e:
            raise LLMError(f"Azure error {e.status_code}: {e.message}") from e
        except o.APIConnectionError as e:
            raise LLMError("Cannot reach Azure - check internet / proxy") from e
        msg = resp.choices[0].message
        if msg.refusal:
            raise LLMError(f"Model declined: {msg.refusal}")
        if msg.parsed is None:
            raise LLMError("Model returned no structured answer")
        u = resp.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        return msg.parsed, Usage(input_tokens=(u.prompt_tokens or 0) - cached,
                                 output_tokens=u.completion_tokens or 0, cache_read=cached,
                                 seconds=time.time() - t0, calls=1)

    if model.startswith("claude-"):
        import anthropic as a
        def conv(c):
            if isinstance(c, str):
                return c
            return [{"type": "text", "text": v} if k == "text" else _image_block("anthropic", v) for k, v in c]
        client = a.Anthropic(api_key=creds.get("anthropic_api_key"), max_retries=2, timeout=300)
        try:
            with client.beta.messages.stream(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": m["role"], "content": conv(m["content"])} for m in messages],
                output_config={"effort": effort},
                output_format=schema,
            ) as stream:
                msg = stream.get_final_message()
        except a.AuthenticationError as e:
            raise LLMError("Anthropic key rejected - check AI Settings in Admin Panel") from e
        except a.RateLimitError as e:
            raise LLMError("Rate limited by the API, try again shortly") from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Cannot reach the API - check internet / proxy") from e
        if msg.stop_reason == "refusal":
            raise LLMError("Model declined the request")
        if msg.stop_reason == "max_tokens":
            raise LLMError("Answer too long - try a smaller request")
        if msg.parsed_output is None:
            raise LLMError("Model returned no structured answer")
        u = msg.usage
        return msg.parsed_output, Usage(
            input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
            cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
            seconds=time.time() - t0, calls=1)

    raise LLMError(f"No provider for model '{model}'")


def make_llm(model: str, effort: str = "high") -> VisionLLM:
    """Pick a provider from the model name: 'claude-*' or 'azure:<deployment>'."""
    if model.startswith("claude-"):
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise LLMError("ANTHROPIC_API_KEY is not set")
        return AnthropicVision(model=model, effort=effort)
    if model.startswith("azure:"):
        return AzureOpenAIVision(model.split(":", 1)[1], effort=effort)
    raise LLMError(f"No provider for model '{model}' (use claude-* or azure:<deployment>)")
