import pytest

from product_card.grounding import _measurements, validate_draft
from product_card.models import Draft, ProductInput


@pytest.fixture
def product():
    return ProductInput(
        name="Термометр",
        manufacturer="Testo",
        specs={"диапазон": "-50 до +350 °C", "питание": "3 AAA"},
        description="Термометр для измерения температуры воды. Корпус ABS. Масса 80 г.",
    )


@pytest.fixture
def draft():
    return Draft(
        seo_title="Термометр Testo",
        seo_description="Измерение температуры воды. " * 34,
        search_queries=["термометр Testo", "термометр для воды", "купить термометр"],
        commercial="Термометр для измерения температуры воды.",
        additional_specs=[],
        missing_fields=[],
        conflicts=[],
        insufficient_data=False,
        evidence={
            "seo_title": ["name", "manufacturer"],
            "seo_description": ["description"],
            "search_queries": ["name"],
            "commercial": ["description"],
        },
    )


def test_valid_source_grounded_draft(product, draft):
    assert validate_draft(product, draft) == []


@pytest.mark.parametrize("length,valid", [(0, False), (70, True), (71, False)])
def test_title_length_boundary(product, draft, length, valid):
    draft.seo_title = "Т" * length
    assert ("seo_title_length" not in validate_draft(product, draft)) is valid


@pytest.mark.parametrize("length,valid", [(799, False), (800, True), (1200, True), (1201, False)])
def test_description_length_boundary(product, draft, length, valid):
    draft.seo_description = "Т" * length
    assert ("seo_description_length" not in validate_draft(product, draft)) is valid


def test_new_technical_number_rejected(product, draft):
    draft.commercial = "Измеряет температуру до 900 °C."
    assert "unsupported_numeric_value" in validate_draft(product, draft)


def test_model_suffix_before_russian_preposition_is_not_time_measurement():
    assert ("1", "с") not in _measurements("testo 905-T1 с погружным зондом")
    assert ("10", "с") in _measurements("отклик 10 с в воде")


def test_model_suffix_with_multiple_digits_is_not_time_measurement():
    assert _measurements("прибор T12 с датчиком") == set()


def test_existing_number_with_wrong_unit_rejected(product, draft):
    draft.commercial = "Питание 350 В."
    assert "unsupported_measurement" in validate_draft(product, draft)


def test_wrong_battery_count_not_borrowed_from_other_spec(product, draft):
    product.specs["толщина"] = "2 мм"
    draft.seo_description += " Питание: 2 батарейки AAA."
    assert "unsupported_battery_count" in validate_draft(product, draft)


def test_equivalent_battery_wording_is_accepted(product, draft):
    draft.seo_description += " Питание: 3 батарейки AAA."
    assert "unsupported_battery_count" not in validate_draft(product, draft)


def test_range_endpoint_unit_is_allowed(product, draft):
    draft.seo_description += "Измеряет температуру от -50 °C до +350 °C."
    assert validate_draft(product, draft) == []


def test_unknown_interface_rejected(product, draft):
    draft.commercial = "Передаёт показания по Bluetooth."
    assert "unsupported_technical_claim" in validate_draft(product, draft)


def test_unsupported_high_accuracy_claim_is_rejected(product, draft):
    draft.seo_description += " Измеряет с высокой точностью."
    assert "unsupported_quality_claim" in validate_draft(product, draft)


def test_explicit_high_accuracy_claim_is_allowed(product, draft):
    product.description += " Измеряет с высокой точностью."
    draft.seo_description += " Измеряет с высокой точностью."
    assert "unsupported_quality_claim" not in validate_draft(product, draft)


def test_fabricated_extracted_fact_rejected(product, draft):
    draft.additional_specs = [
        {"name": "материал", "value": "сталь", "source_quote": "Корпус сталь."}
    ]
    assert "unverified_additional_spec" in validate_draft(product, draft)


def test_extracted_spec_name_must_be_in_source_quote(product, draft):
    draft.additional_specs = [
        {"name": "длина зонда", "value": "80 г", "source_quote": "Масса 80 г."}
    ]
    assert "unverified_additional_spec" in validate_draft(product, draft)


def test_quoted_fact_is_accepted(product, draft):
    draft.additional_specs = [{"name": "масса", "value": "80 г", "source_quote": "Масса 80 г."}]
    assert validate_draft(product, draft) == []


def test_conflicting_spec_requires_clarification(product, draft):
    product.specs["масса"] = "90 г"
    draft.additional_specs = [{"name": "масса", "value": "80 г", "source_quote": "Масса 80 г."}]
    assert "conflicting_spec" in validate_draft(product, draft)


def test_search_queries_distinct_and_counted(product, draft):
    draft.search_queries = ["термометр", "Термометр", " термометр "]
    assert "search_queries_not_unique" in validate_draft(product, draft)


def test_unknown_source_reference_rejected(product, draft):
    draft.evidence.commercial = ["external_web"]
    assert "invalid_source_reference" in validate_draft(product, draft)


def test_typographic_minus_from_real_generation_is_not_a_new_value(product, draft):
    draft.seo_description += "Температура от –50 °C до +350 °C."
    assert validate_draft(product, draft) == []


def test_ascii_range_separator_is_not_a_negative_endpoint(product, draft):
    product.specs["время"] = "1–2 минуты"
    draft.seo_description += "Допустимое время 1-2 минуты."
    assert validate_draft(product, draft) == []


def test_commercial_avoids_unqualified_measurement_claims(product, draft):
    draft.commercial = "Для специалистов, которым нужна точность ±1 °C."
    assert "commercial_technical_details" in validate_draft(product, draft)


def test_changed_temperature_sign_is_rejected(product, draft):
    draft.commercial = "Температура до -350 °C."
    assert "unsupported_measurement" in validate_draft(product, draft)


def test_probe_immersion_does_not_allow_instrument_immersion(product, draft):
    draft.seo_description += "Можно погружать прибор в жидкости."
    assert "unsupported_technical_claim" in validate_draft(product, draft)


def test_unstated_production_use_case_is_rejected(product, draft):
    draft.commercial = "Для технического контроля в производстве."
    assert "unsupported_use_case" in validate_draft(product, draft)


def test_manufacturer_attribution_is_not_an_industrial_use_case(product, draft):
    draft.seo_description += " Прибор производства Testo."
    assert "unsupported_use_case" not in validate_draft(product, draft)


def test_manufacturer_attribution_does_not_mask_industrial_use(product, draft):
    draft.seo_description += " Прибор производства Testo для работы на производстве."
    assert "unsupported_use_case" in validate_draft(product, draft)


def test_manufacturer_attribution_in_source_does_not_authorize_industrial_use(product, draft):
    product.description += " Прибор производства Testo."
    draft.seo_description += " Для работы на производстве."
    assert "unsupported_use_case" in validate_draft(product, draft)


@pytest.mark.parametrize("claim", ["Ресурс 999h.", "Время 999мин.", "Модель Z999."])
def test_new_number_attached_to_letters_is_rejected(product, draft, claim):
    draft.seo_description += claim
    assert "unsupported_numeric_value" in validate_draft(product, draft)


def test_commercial_is_selected_from_source_excerpt_options(product, draft):
    draft.commercial = "Прибор для неизвестных целей."
    assert "commercial_not_source_excerpt" in validate_draft(product, draft)


def test_equivalent_unit_spelling_is_not_a_different_measurement(product, draft):
    product.specs["диаметр"] = "3 мм"
    draft.seo_description += "Диаметр 3mm."
    assert validate_draft(product, draft) == []


def test_pressure_prefix_case_preserves_scale(product, draft):
    product.specs["давление"] = "1 МПа"
    draft.seo_description += "Давление 1 мПа."
    assert "unsupported_measurement" in validate_draft(product, draft)


def test_negative_temperature_after_word_preserves_sign(product, draft):
    draft.seo_description += "Работает при-50 °C."
    assert validate_draft(product, draft) == []
