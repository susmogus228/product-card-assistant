import json

import pytest

from product_card.errors import InputError
from product_card.models import parse_product


def test_preserves_specs_and_marks_blank_fields():
    product = parse_product(
        json.dumps(
            {
                "name": "  Прибор  ",
                "manufacturer": " ",
                "specs": {"диапазон": "0–1,6 МПа", "питание": " "},
                "description": None,
            }
        )
    )
    assert product.name == "Прибор"
    assert product.specs == {"диапазон": "0–1,6 МПа", "питание": None}
    assert product.missing_fields() == ["manufacturer", "description", "specs.питание"]


@pytest.mark.parametrize(
    "raw",
    [
        '{"name":',
        "[]",
        "null",
        '{"name": 123}',
        '{"name":"A","name":"B"}',
        '{"name":"A","specs":{"x":NaN}}',
        '{"name":"A","specs":{"x":1.5}}',
        '{"name":"A","specs":[]}',
        '{"name":"A","unknown":"x"}',
        '{"name":"A","specs":{" ":"x"}}',
    ],
)
def test_rejects_invalid_json_and_types(raw):
    with pytest.raises(InputError):
        parse_product(raw)


def test_rejects_oversized_input_before_parsing():
    with pytest.raises(InputError, match="размер"):
        parse_product(" " * 262145)


def test_accepts_bom_and_empty_input_as_missing_data():
    product = parse_product("\ufeff{}")
    assert product.missing_fields() == ["name", "manufacturer", "description", "specs"]


def test_rejects_ambiguous_spec_names():
    raw = '{"name":"Прибор","specs":{"масса":"80 г"," Масса ":"90 г"}}'
    with pytest.raises(InputError):
        parse_product(raw)
