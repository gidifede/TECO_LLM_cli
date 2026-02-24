"""Chiamata ad Azure OpenAI via SDK openai — con supporto multi-turn."""

from dataclasses import dataclass

from openai import AzureOpenAI

from .config import AzureOpenAIConfig


@dataclass
class LLMResponse:
    """Risposta da Azure OpenAI con contenuto e motivo di fine generazione."""

    content: str
    finish_reason: str  # "stop" = completo, "length" = troncato per max_tokens
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


def _build_client(config: AzureOpenAIConfig) -> AzureOpenAI:
    return AzureOpenAI(
        api_key=config.api_key,
        azure_endpoint=config.endpoint,
        api_version=config.api_version,
    )


def _model_flags(deployment: str) -> tuple[bool, bool]:
    """Restituisce (is_restricted, is_new_api) in base al nome del deployment."""
    is_restricted = deployment.startswith(("gpt-5-mini", "o1", "o3", "o4"))
    is_new_api = deployment.startswith(("gpt-5", "o1", "o3", "o4"))
    return is_restricted, is_new_api


def call_azure_openai(
    config: AzureOpenAIConfig,
    user_content: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Esegue una singola chiamata chat completions su Azure OpenAI.

    Restituisce un LLMResponse con il contenuto e il finish_reason.
    """
    client = _build_client(config)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    is_restricted, is_new_api = _model_flags(config.deployment)
    token_param = "max_completion_tokens" if is_new_api else "max_tokens"

    kwargs: dict = {
        "model": config.deployment,
        "messages": messages,
        token_param: max_tokens,
    }
    if not is_restricted:
        kwargs["temperature"] = temperature

    response = client.chat.completions.create(**kwargs)

    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        content=choice.message.content or "",
        finish_reason=choice.finish_reason or "unknown",
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
    )


def call_azure_openai_chat(
    config: AzureOpenAIConfig,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Chiamata multi-turn: accetta una lista completa di messaggi.

    I messaggi seguono il formato OpenAI:
    [{"role": "system"|"user"|"assistant", "content": "..."}]

    Usato per l'intervistatore (che accumula history) e lo stakeholder.
    """
    client = _build_client(config)

    is_restricted, is_new_api = _model_flags(config.deployment)
    token_param = "max_completion_tokens" if is_new_api else "max_tokens"

    kwargs: dict = {
        "model": config.deployment,
        "messages": messages,
        token_param: max_tokens,
    }
    if not is_restricted:
        kwargs["temperature"] = temperature

    response = client.chat.completions.create(**kwargs)

    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        content=choice.message.content or "",
        finish_reason=choice.finish_reason or "unknown",
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
    )
