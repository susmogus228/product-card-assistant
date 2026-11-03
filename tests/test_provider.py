import json

import httpx
import pytest
from groq import Groq

from product_card.errors import ModelOutputError, ProviderError
from product_card.provider import GroqProvider


def completion(content, finish_reason="stop"):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def test_real_sdk_sends_strict_schema_and_untrusted_product_in_user_message(
    sample_product,
    valid_draft,
):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/openai/v1/chat/completions"
        assert body["model"] == "openai/gpt-oss-120b"
        assert body["response_format"]["json_schema"]["strict"] is True
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["seo_title"]["maxLength"] == 70
        assert schema["properties"]["seo_description"]["maxLength"] == 1200
        assert (
            "Термометр для измерения температуры воды."
            in (schema["properties"]["commercial"]["enum"])
        )
        allowed = schema["$defs"]["Evidence"]["properties"]["seo_title"]["items"]["enum"]
        assert "name" in allowed
        assert "specs.питание" in allowed
        assert "external_web" not in allowed
        payload = json.loads(body["messages"][1]["content"])
        assert payload["product"]["specs"]["питание"] == "3 AAA"
        assert "Термометр для измерения" not in body["messages"][0]["content"]
        return httpx.Response(200, json=completion(valid_draft.model_dump_json()))

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        result = GroqProvider(client).generate(sample_product)
    assert result.seo_title == "Термометр Testo"


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_api_errors_are_safe_and_actionable(sample_product, status):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "SECRET_PROVIDER_BODY"}})

    with Groq(
        api_key="SECRET_TEST_KEY",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ProviderError) as error:
            GroqProvider(client).generate(sample_product)
    assert "SECRET" not in str(error.value)
    assert str(error.value)


def test_timeout_is_safe(sample_product):
    def handler(request):
        raise httpx.ReadTimeout("SECRET_REQUEST", request=request)

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ProviderError, match="время"):
            GroqProvider(client).generate(sample_product)


@pytest.mark.parametrize(
    "content,finish",
    [
        ("not json", "stop"),
        ("{}", "stop"),
        (None, "stop"),
        ('{"ok":', "length"),
    ],
)
def test_invalid_and_truncated_model_output_rejected(sample_product, content, finish):
    def handler(request):
        return httpx.Response(200, json=completion(content, finish))

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ModelOutputError):
            GroqProvider(client).generate(sample_product)


@pytest.mark.parametrize("body", ["not-json", "{}", '{"choices":[{}]}'])
def test_broken_http_success_body_does_not_escape_as_traceback(sample_product, body):
    def handler(request):
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ModelOutputError):
            GroqProvider(client).generate(sample_product)


@pytest.mark.parametrize("message", [None, {}, {"role": "assistant", "content": None}])
def test_http_success_with_missing_message_content_is_safe(sample_product, message):
    body = completion(None)
    body["choices"][0]["message"] = message

    def handler(request):
        return httpx.Response(200, json=body)

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ModelOutputError):
            GroqProvider(client).generate(sample_product)


def test_provider_schema_validation_error_is_repairable(sample_product):
    def handler(request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "json_validate_failed",
                    "message": "PRIVATE_GENERATION",
                }
            },
        )

    with Groq(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ModelOutputError) as error:
            GroqProvider(client).generate(sample_product)
    assert "PRIVATE_GENERATION" not in str(error.value)
