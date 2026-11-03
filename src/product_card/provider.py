import json

from groq import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    Groq,
)
from pydantic import ValidationError

from product_card.errors import InputError, ModelOutputError, ProviderError
from product_card.models import Draft, ProductInput
from product_card.prompts import SYSTEM_PROMPT
from product_card.source_text import commercial_options


def _transport_schema(product: ProductInput) -> dict:
    # Mirror tested SEO text bounds in the provider schema; keep other limits local.
    schema = Draft.model_json_schema()
    for field in schema["$defs"]["Evidence"]["properties"].values():
        field["items"]["enum"] = list(product.sources())
    unsupported = {
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    }

    def simplify(node):
        if isinstance(node, dict):
            return {key: simplify(value) for key, value in node.items() if key not in unsupported}
        if isinstance(node, list):
            return [simplify(value) for value in node]
        return node

    result = simplify(schema)
    result["properties"]["seo_title"]["maxLength"] = 70
    # A same-type anyOf for empty-or-800+ text was rejected by the live provider.
    # Keep the upper bound here and enforce the 800-character minimum locally.
    result["properties"]["seo_description"] = {"type": "string", "maxLength": 1200}
    result["properties"]["commercial"]["maxLength"] = 600
    options = commercial_options(product.description)
    if options:
        result["properties"]["commercial"]["enum"] = options
    return result


class GroqProvider:
    def __init__(self, client: Groq | None, model: str = "openai/gpt-oss-120b"):
        self.client = client
        self.model = model

    def generate(self, product: ProductInput, repair_errors=()) -> Draft:
        if self.client is None:
            raise InputError("Задайте GROQ_API_KEY в переменной окружения или локальном .env.")
        payload = {
            "product": product.model_dump(),
            "source_ids": list(product.sources()),
            "repair_errors": list(repair_errors),
            "commercial_options": commercial_options(product.description),
        }
        guidance = {
            "commercial_technical_details": "Rewrite commercial as audience and tasks only. "
            "Remove technical measurements, ranges and accuracy claims from commercial.",
            "unverified_additional_spec": "Return additional_specs=[] if uncertain. Values must "
            "be contiguous literal substrings of exact source quotes, without omitted words.",
            "seo_description_length": "seo_description must have 800-1200 characters including "
            "spaces. Target 900-1050 characters using only supplied facts.",
        }
        payload["repair_guidance"] = [guidance[code] for code in repair_errors if code in guidance]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0,
                reasoning_effort="low",
                max_completion_tokens=2800,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "product_card_draft",
                        "strict": True,
                        "schema": _transport_schema(product),
                    },
                },
            )
        except APITimeoutError as exc:
            raise ProviderError("Истекло время ожидания Groq. Повторите запуск позже.") from exc
        except APIConnectionError as exc:
            raise ProviderError(
                "Нет соединения с Groq. Проверьте сеть и повторите запуск."
            ) from exc
        except (APIResponseValidationError, json.JSONDecodeError) as exc:
            raise ModelOutputError("Groq вернул повреждённый ответ.") from exc
        except APIStatusError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            if (
                exc.status_code == 400
                and isinstance(error, dict)
                and error.get("code") == "json_validate_failed"
            ):
                raise ModelOutputError("Ответ модели не прошёл проверку схемы Groq.") from exc
            messages = {
                401: "Ключ Groq не принят. Проверьте GROQ_API_KEY в локальном .env.",
                403: "Groq запретил доступ. Проверьте разрешения аккаунта и модели.",
                429: "Достигнут лимит Groq. Подождите и повторите запуск.",
            }
            message = messages.get(exc.status_code)
            if message is None:
                message = (
                    "Groq временно недоступен. Повторите запуск позже."
                    if exc.status_code >= 500
                    else "Groq отклонил запрос. Проверьте модель и совместимость схемы."
                )
            raise ProviderError(message) from exc

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise ModelOutputError("Модель вернула неполный ответ или отказ.")
        choice = choices[0]
        if getattr(choice, "finish_reason", None) != "stop":
            raise ModelOutputError("Модель вернула неполный ответ или отказ.")
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if getattr(message, "refusal", None) or not isinstance(content, str) or not content.strip():
            raise ModelOutputError("Модель не вернула карточку или отказалась от генерации.")
        try:
            return Draft.model_validate_json(content)
        except (ValidationError, ValueError) as exc:
            raise ModelOutputError("Модель вернула ответ неверной структуры.") from exc
