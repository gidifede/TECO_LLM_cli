"""Chiamata ad Azure OpenAI via SDK openai."""

from dataclasses import dataclass

from openai import AzureOpenAI

from .config import AzureOpenAIConfig


@dataclass
class LLMResponse:
    """Risposta da Azure OpenAI con contenuto e motivo di fine generazione."""

    content: str
    finish_reason: str  # "stop" = completo, "length" = troncato per max_tokens

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


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
    client = AzureOpenAI(
        api_key=config.api_key,
        azure_endpoint=config.endpoint,
        api_version=config.api_version,
    )

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    # Alcuni modelli hanno restrizioni sui parametri supportati.
    # - gpt-5*, o-series: max_completion_tokens invece di max_tokens
    # - gpt-5-mini, o-series: temperature non supportata (solo default 1)
    is_restricted = config.deployment.startswith(("gpt-5-mini", "o1", "o3", "o4"))
    is_new_api = config.deployment.startswith(("gpt-5", "o1", "o3", "o4"))

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
    return LLMResponse(
        content=choice.message.content or "",
        finish_reason=choice.finish_reason or "unknown",
    )
