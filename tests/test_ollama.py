import json

import httpx
import pytest

from product_card.errors import InputError, ModelOutputError, ProviderError
from product_card.models import ProductInput
from product_card.ollama_provider import (
    OllamaProvider,
    _filter_extraction,
    _ground_accessory,
    _ground_accuracy,
    _ground_humidity,
    _ground_probe,
    _ground_quality,
    _ground_scope,
    _review_text,
    check_ollama_url,
)
from product_card.render import render_markdown
from product_card.service import generate_card


def test_ollama_extracts_verified_fact_and_builds_draft(sample_product, valid_draft):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == "/api/chat"
        assert body["stream"] is False
        if len(calls) == 1:
            extraction_input = json.loads(body["messages"][1]["content"])
            assert extraction_input["description"] == sample_product.description
            assert "питание" in extraction_input["existing_spec_names"]
            assert "specs" not in extraction_input
            content = {
                "additional_specs": [
                    {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."}
                ]
            }
        else:
            content = valid_draft.model_dump()
            assert body["format"]["properties"]["additional_specs"]["maxItems"] == 0
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        draft = OllamaProvider(client, "http://127.0.0.1:11434", "test-model").generate(
            sample_product
        )
    assert len(calls) == 2
    assert draft.additional_specs[0].value == "80 г"
    assert draft.additional_specs[0].source_quote == "Масса 80 г."


def test_incomplete_accuracy_sentence_uses_verbatim_source(valid_draft):
    product = ProductInput(
        name="Прибор",
        specs={
            "погрешность температуры": (
                "±0,5 °C при +25 °C; дополнительно ±1 единица младшего разряда"
            ),
            "погрешность влажности": "±3 %RH при +25 °C; дополнительно ±1 единица младшего разряда",
        },
        description="Прибор измеряет температуру и влажность.",
    )
    valid_draft.seo_description = (
        "Прибор измеряет температуру. Погрешность ±0,5 °C и ±3 %RH при +25 °C. "
        "Подходит для помещений."
    )
    _ground_accuracy(product, valid_draft)
    assert product.specs["погрешность температуры"] in valid_draft.seo_description
    assert product.specs["погрешность влажности"] in valid_draft.seo_description
    assert "Погрешность ±0,5 °C и ±3 %RH при +25 °C." not in valid_draft.seo_description
    assert "Подходит для помещений." in valid_draft.seo_description


def test_unknown_accuracy_is_not_invented(valid_draft):
    product = ProductInput(name="Прибор", specs={}, description="Измерение температуры.")
    valid_draft.seo_description = "Погрешность ±0,5 °C."
    original = valid_draft.seo_description
    _ground_accuracy(product, valid_draft)
    assert valid_draft.seo_description == original


def test_qualified_accuracy_is_preserved(valid_draft):
    product = ProductInput(
        name="Прибор",
        specs={"погрешность": "±0,5 °C; дополнительно ±1 единица младшего разряда"},
        description="Прибор измеряет температуру.",
    )
    valid_draft.seo_description = "Погрешность ±0,5 °C; дополнительно ±1 единица младшего разряда."
    original = valid_draft.seo_description
    _ground_accuracy(product, valid_draft)
    assert valid_draft.seo_description == original


def test_humidity_condition_is_added_only_to_matching_range(valid_draft):
    product = ProductInput(
        name="Прибор",
        specs={"диапазон влажности": "10 до 95 %RH без конденсации"},
        description="Измерение влажности.",
    )
    valid_draft.seo_description = "Влажность 10 до 95 %RH."
    _ground_humidity(product, valid_draft)
    assert valid_draft.seo_description == "Влажность 10 до 95 %RH без конденсации."
    assert "specs.диапазон влажности" in valid_draft.evidence.seo_description


def test_single_humidity_value_does_not_require_range_condition(valid_draft):
    product = ProductInput(
        name="Прибор",
        specs={"диапазон влажности": "10 до 95 %RH без конденсации"},
        description="Измерение влажности.",
    )
    valid_draft.seo_description = "Разрешение составляет 0,1 %RH."
    _review_text(product, valid_draft)


def test_other_humidity_range_does_not_get_source_condition(valid_draft):
    product = ProductInput(
        name="Прибор",
        specs={"диапазон влажности": "10 до 95 %RH без конденсации"},
        description="Измерение влажности.",
    )
    valid_draft.seo_description = "Влажность 0 до 100 %RH."
    _ground_humidity(product, valid_draft)
    assert "без конденсации" not in valid_draft.seo_description
    with pytest.raises(ModelOutputError):
        _review_text(product, valid_draft)


def test_unconfirmed_accessory_is_replaced_with_verbatim_source(valid_draft):
    source = "Для измерений требуется трубка Пито; она не заявлена как входящая в комплект."
    product = ProductInput(name="Прибор", description=source)
    valid_draft.seo_description = "Используется трубка Пито, не входящая в комплект."
    _ground_accessory(product, valid_draft)
    assert valid_draft.seo_description == source
    assert "description" in valid_draft.evidence.seo_description


def test_scenario_limit_is_not_changed_into_absolute_claim(valid_draft):
    source = "Документирование не относится к описанному сценарию."
    product = ProductInput(name="Прибор", description=source)
    valid_draft.seo_description = "Документирование не предусмотрено."
    _ground_scope(product, valid_draft)
    assert valid_draft.seo_description == source


def test_ambiguous_probe_sentence_uses_exact_source(valid_draft):
    source = "Зонд можно погружать в жидкость; также его можно вводить в вентиляционные каналы."
    product = ProductInput(name="Термометр", description=source)
    valid_draft.seo_description = (
        "Зонд допускается погружать в жидкости, а также вентиляционные каналы."
    )
    _ground_probe(product, valid_draft)
    assert valid_draft.seo_description == source


def test_correct_probe_sentence_is_not_rewritten(valid_draft):
    source = "Зонд можно погружать в жидкость; также его можно вводить в вентиляционные каналы."
    product = ProductInput(name="Термометр", description=source)
    valid_draft.seo_description = "Зонд можно вводить в вентиляционные каналы."
    original = valid_draft.seo_description
    _ground_probe(product, valid_draft)
    assert valid_draft.seo_description == original


def test_unsupported_accuracy_superlative_is_removed(valid_draft):
    product = ProductInput(name="Прибор", description="Измеряет давление.")
    valid_draft.seo_description = "Прибор измеряет давление с высокой точностью."
    _ground_quality(product, valid_draft)
    assert valid_draft.seo_description == "Прибор измеряет давление."


def test_sourced_accuracy_superlative_is_preserved(valid_draft):
    product = ProductInput(name="Прибор", description="Измеряет с высокой точностью.")
    valid_draft.seo_description = "Измеряет с высокой точностью."
    _ground_quality(product, valid_draft)
    assert valid_draft.seo_description == "Измеряет с высокой точностью."


def test_ollama_ignores_duplicate_existing_fields(sample_product, valid_draft):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            content = {
                "additional_specs": [
                    {"name": "питание", "value": "батарейка", "source_quote": "not a real quote"},
                    {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."},
                ]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        draft = OllamaProvider(client, "http://127.0.0.1:11434", "test-model").generate(
            sample_product
        )
    assert [item.name for item in draft.additional_specs] == ["Масса"]


@pytest.mark.parametrize("quote,value", [("Масса 900 г.", "900 г"), ("Масса 80 г.", "900 г")])
def test_ollama_discards_fabricated_extraction_with_warning(
    sample_product, valid_draft, quote, value
):
    def handler(request):
        body = json.loads(request.content)
        if (
            "additional_specs" in body["format"].get("properties", {})
            and "seo_title" not in body["format"]["properties"]
        ):
            content = {
                "additional_specs": [{"name": "масса", "value": value, "source_quote": quote}]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(client, "http://127.0.0.1:11434", "test-model")
        card = generate_card(sample_product, provider)
    assert not any(item.name == "масса" for item in card.characteristics)
    assert any("неподтвержд" in warning.casefold() for warning in card.warnings)
    assert "900" not in " ".join(card.warnings)


def test_mixed_candidates_keep_grounded_values_and_report_rejected(sample_product, valid_draft):
    def handler(request):
        body = json.loads(request.content)
        if "seo_title" not in body["format"]["properties"]:
            content = {
                "additional_specs": [
                    {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."},
                    {"name": "Защита", "value": "IP68", "source_quote": "Защита IP68."},
                ]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        card = generate_card(
            sample_product, OllamaProvider(client, "http://127.0.0.1:11434", "test-model")
        )
    assert any(item.name == "Масса" and item.value == "80 г" for item in card.characteristics)
    assert not any(item.name == "Защита" for item in card.characteristics)
    assert any("неподтвержд" in warning.casefold() for warning in card.warnings)
    assert "неподтверждённые характеристики исключены" in render_markdown(card)


def test_literal_duplicate_conflicting_with_input_needs_clarification(sample_product, valid_draft):
    sample_product.specs["масса"] = "90 г"

    def handler(request):
        body = json.loads(request.content)
        if "seo_title" not in body["format"]["properties"]:
            content = {
                "additional_specs": [
                    {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."}
                ]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        card = generate_card(
            sample_product, OllamaProvider(client, "http://127.0.0.1:11434", "test-model")
        )
    assert card.status == "needs_data"
    assert card.seo_description is None
    assert (
        next(item for item in card.characteristics if item.name == "масса").value
        == "требует уточнения"
    )


def test_malformed_candidate_does_not_erase_valid_candidate(sample_product, valid_draft):
    def handler(request):
        body = json.loads(request.content)
        if "seo_title" not in body["format"]["properties"]:
            content = {
                "additional_specs": [
                    {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."},
                    {"name": "wrong", "value": None, "source_quote": "bad"},
                ]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        card = generate_card(
            sample_product, OllamaProvider(client, "http://127.0.0.1:11434", "test-model")
        )
    assert any(item.name == "Масса" and item.value == "80 г" for item in card.characteristics)
    assert any("неподтвержд" in warning.casefold() for warning in card.warnings)


def test_conflicting_new_values_are_not_silently_selected(sample_product):
    sample_product.description = "Масса 80 г. Масса 90 г."
    content = json.dumps(
        {
            "additional_specs": [
                {"name": "масса", "value": "80 г", "source_quote": "Масса 80 г."},
                {"name": "масса", "value": "90 г", "source_quote": "Масса 90 г."},
            ]
        },
        ensure_ascii=False,
    )
    values, conflicts, rejected, ambiguous = _filter_extraction(sample_product, content)
    assert values == []
    assert conflicts == []
    assert rejected == 0
    assert ambiguous is True


def test_identical_new_values_are_deduplicated(sample_product):
    item = {"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."}
    values, conflicts, rejected, ambiguous = _filter_extraction(
        sample_product, json.dumps({"additional_specs": [item, item]}, ensure_ascii=False)
    )
    assert len(values) == 1
    assert not conflicts and rejected == 0 and not ambiguous


def test_conflicting_new_values_suppress_generated_card(sample_product, valid_draft):
    sample_product.description = "Масса 80 г. Масса 90 г."

    def handler(request):
        body = json.loads(request.content)
        if "seo_title" not in body["format"]["properties"]:
            content = {
                "additional_specs": [
                    {"name": "масса", "value": "80 г", "source_quote": "Масса 80 г."},
                    {"name": "масса", "value": "90 г", "source_quote": "Масса 90 г."},
                ]
            }
        else:
            content = valid_draft.model_dump()
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(content, ensure_ascii=False)},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        card = generate_card(
            sample_product, OllamaProvider(client, "http://127.0.0.1:11434", "test-model")
        )
    assert card.status == "needs_data"
    assert card.seo_description is None
    assert not any(item.name == "масса" for item in card.characteristics)
    assert any("противоречив" in field for field in card.missing_fields)


def test_absent_information_is_not_added_as_characteristic(sample_product):
    sample_product.description += " Сведения о гарантии отсутствуют."
    content = json.dumps(
        {
            "additional_specs": [
                {
                    "name": "гарантии",
                    "value": "отсутствуют",
                    "source_quote": "Сведения о гарантии отсутствуют.",
                }
            ]
        },
        ensure_ascii=False,
    )
    values, _, rejected, _ = _filter_extraction(sample_product, content)
    assert not values
    assert rejected == 1


def test_usage_instruction_is_not_an_additional_spec(sample_product):
    sample_product.description += " Зонд можно погружать в жидкость."
    content = json.dumps(
        {
            "additional_specs": [
                {
                    "name": "Зонд",
                    "value": "можно погружать в жидкость",
                    "source_quote": "Зонд можно погружать в жидкость.",
                }
            ]
        },
        ensure_ascii=False,
    )
    values, _, rejected, _ = _filter_extraction(sample_product, content)
    assert values == []
    assert rejected == 1


def test_response_time_qualifier_does_not_duplicate_existing_spec(sample_product):
    sample_product.specs["время отклика"] = "t99 около 10 с в воде"
    sample_product.description += " Время отклика t99 около 10 с в воде."
    content = json.dumps(
        {
            "additional_specs": [
                {
                    "name": "Время отклика t99",
                    "value": "около 10 с в воде",
                    "source_quote": "Время отклика t99 около 10 с в воде.",
                }
            ]
        },
        ensure_ascii=False,
    )
    values, conflicts, rejected, ambiguous = _filter_extraction(sample_product, content)
    assert values == []
    assert conflicts == []
    assert rejected == 0 and not ambiguous


def test_response_time_qualifier_with_different_value_needs_review(sample_product):
    sample_product.specs["время отклика"] = "t99 около 10 с в воде"
    sample_product.description += " Время отклика t99 около 20 с в воде."
    content = json.dumps(
        {
            "additional_specs": [
                {
                    "name": "Время отклика t99",
                    "value": "около 20 с в воде",
                    "source_quote": "Время отклика t99 около 20 с в воде.",
                }
            ]
        },
        ensure_ascii=False,
    )
    values, conflicts, rejected, ambiguous = _filter_extraction(sample_product, content)
    assert values == []
    assert len(conflicts) == 1 and conflicts[0].spec_name == "время отклика"
    assert rejected == 0 and not ambiguous


def test_response_time_does_not_treat_10_as_part_of_110(sample_product):
    sample_product.specs["время отклика"] = "t99 110 с"
    sample_product.description += " Время отклика t99 10 с."
    content = json.dumps(
        {
            "additional_specs": [
                {
                    "name": "Время отклика t99",
                    "value": "10 с",
                    "source_quote": "Время отклика t99 10 с.",
                }
            ]
        },
        ensure_ascii=False,
    )
    values, conflicts, _, _ = _filter_extraction(sample_product, content)
    assert not values and len(conflicts) == 1


def test_quote_cannot_hide_a_negation_in_the_same_sentence(sample_product):
    sample_product.description = "Масса 80 г не подтверждена."
    content = json.dumps(
        {"additional_specs": [{"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г"}]},
        ensure_ascii=False,
    )
    values, _, rejected, _ = _filter_extraction(sample_product, content)
    assert values == []
    assert rejected == 1


def test_unrelated_missing_field_does_not_reject_supported_sentence(sample_product):
    sample_product.description = "Масса 80 г. Питание не указано."
    content = json.dumps(
        {"additional_specs": [{"name": "Масса", "value": "80 г", "source_quote": "Масса 80 г."}]},
        ensure_ascii=False,
    )
    values, _, rejected, _ = _filter_extraction(sample_product, content)
    assert len(values) == 1
    assert rejected == 0


@pytest.mark.parametrize("content", ["not json", "{}", '{"additional_specs":"bad"}'])
def test_invalid_extraction_envelope_is_rejected(sample_product, content):
    with pytest.raises(ModelOutputError):
        _filter_extraction(sample_product, content)


@pytest.mark.parametrize("status", [401, 404, 429, 500])
def test_ollama_errors_do_not_disclose_response(sample_product, status):
    def handler(request):
        return httpx.Response(status, json={"error": "SECRET_PROVIDER_BODY"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as exc:
            OllamaProvider(client, "http://127.0.0.1:11434", "test-model").generate(sample_product)
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://user:password@localhost:11434",
        "http://localhost:11434/?token=secret",
        "file:///tmp/api",
        "https://localhost/#token",
        "http://[broken",
    ],
)
def test_ollama_url_rejects_embedded_credentials(url):
    with pytest.raises(InputError):
        check_ollama_url(url)
