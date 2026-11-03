import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from product_card.errors import InputError

MAX_INPUT_BYTES = 262144


def normalize_spec_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class ProductInput(StrictModel):
    name: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=200)
    specs: dict[str, str | None] = Field(default_factory=dict, max_length=64)
    description: str | None = Field(default=None, max_length=20000)

    @field_validator("name", "manufacturer", "description", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("specs")
    @classmethod
    def normalize_specs(cls, specs):
        names = set()
        for key, value in specs.items():
            if not key.strip() or len(key) > 160:
                raise ValueError("invalid specification name")
            normalized = normalize_spec_name(key)
            if normalized in names:
                raise ValueError("ambiguous specification names")
            names.add(normalized)
            if value is not None and len(value) > 1000:
                raise ValueError("specification value too long")
        return {key: value if value and value.strip() else None for key, value in specs.items()}

    def missing_fields(self) -> list[str]:
        missing = [key for key in ("name", "manufacturer", "description") if not getattr(self, key)]
        if not self.specs:
            missing.append("specs")
        missing.extend(f"specs.{key}" for key, value in self.specs.items() if value is None)
        return missing

    def sources(self) -> dict[str, str]:
        sources = {
            key: getattr(self, key)
            for key in ("name", "manufacturer", "description")
            if getattr(self, key)
        }
        sources.update({f"specs.{key}": value for key, value in self.specs.items() if value})
        return sources


class AdditionalSpec(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=1000)
    source_quote: str = Field(min_length=3, max_length=1200)


class Conflict(StrictModel):
    spec_name: str = Field(min_length=1, max_length=160)
    description_value: str = Field(min_length=1, max_length=1000)
    source_quote: str = Field(min_length=3, max_length=1200)


class Evidence(StrictModel):
    seo_title: list[str]
    seo_description: list[str]
    search_queries: list[str]
    commercial: list[str]


class Draft(StrictModel):
    # Business lengths are checked locally so a rejected generation can be repaired.
    seo_title: str = Field(max_length=500)
    seo_description: str = Field(max_length=4000)
    search_queries: list[str] = Field(max_length=10)
    commercial: str = Field(max_length=1500)
    additional_specs: list[AdditionalSpec] = Field(max_length=30)
    missing_fields: list[str] = Field(max_length=20)
    conflicts: list[Conflict] = Field(max_length=20)
    insufficient_data: bool
    evidence: Evidence


class Characteristic(StrictModel):
    name: str
    value: str
    source: str


class ProductCard(StrictModel):
    status: Literal["draft", "needs_data"]
    product_name: str
    manufacturer: str
    seo_title: str | None
    seo_description: str | None
    characteristics: list[Characteristic]
    search_queries: list[str]
    commercial: str | None
    missing_fields: list[str]
    warnings: list[str]
    evidence: dict[str, list[str]]
    validation: dict[str, int | bool]
    model: str | None
    generation_attempts: int


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("non-standard JSON number")


def parse_product(raw: str) -> ProductInput:
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InputError("Превышен допустимый размер JSON: 256 КиБ.")
    try:
        data = json.loads(
            raw.removeprefix("\ufeff"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise InputError("Некорректный JSON: проверьте синтаксис и повторяющиеся ключи.") from exc
    try:
        return ProductInput.model_validate(data)
    except (ValidationError, RecursionError) as exc:
        raise InputError(
            "Неверная структура: ожидается объект с name, manufacturer, specs, description; "
            "текстовые значения должны быть строками или null, specs должен быть объектом. "
            "Неизвестные поля, пустые имена характеристик и слишком длинные значения запрещены."
        ) from exc
