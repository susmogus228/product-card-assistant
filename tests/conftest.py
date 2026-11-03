import pytest

from product_card.models import Draft, ProductInput


@pytest.fixture
def sample_product():
    return ProductInput(
        name="Термометр",
        manufacturer="Testo",
        specs={"диапазон": "-50 до +350 °C", "питание": "3 AAA"},
        description="Термометр для измерения температуры воды. Корпус ABS. Масса 80 г.",
    )


@pytest.fixture
def valid_draft():
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
