import re
from typing import Protocol

from product_card.errors import ModelOutputError
from product_card.grounding import validate_draft, verified_conflicts
from product_card.models import (
    Characteristic,
    Draft,
    ProductCard,
    ProductInput,
    normalize_spec_name,
)


class Provider(Protocol):
    model: str

    def generate(self, product: ProductInput, repair_errors=()) -> Draft: ...


def _characteristics(product: ProductInput, draft: Draft | None, conflicts=()):
    result = {
        name: Characteristic(
            name=name,
            value=value or "данных нет",
            source=f"specs.{name}",
        )
        for name, value in product.specs.items()
    }
    if draft is not None:
        for spec in draft.additional_specs:
            existing = next(
                (
                    name
                    for name in result
                    if normalize_spec_name(name) == normalize_spec_name(spec.name)
                ),
                None,
            )
            if existing is None or result[existing].value == "данных нет":
                name = existing or spec.name
                result[name] = Characteristic(
                    name=name,
                    value=spec.value,
                    source=f"description: {spec.source_quote}",
                )
    for name in conflicts:
        if name in result:
            result[name] = Characteristic(
                name=name,
                value="требует уточнения",
                source=f"specs.{name} / description",
            )
    if not result:
        return [Characteristic(name="характеристики", value="данных нет", source="missing")]
    return list(result.values())


def _card(product, provider, draft=None, attempts=0, conflicts=(), warnings=()):
    needs_data = draft is None or draft.insufficient_data or bool(conflicts)
    characteristics = _characteristics(product, draft, conflicts)
    missing = product.missing_fields()
    if draft is not None:
        missing.extend(draft.missing_fields)
        resolved = {
            f"specs.{item.name}"
            for item in characteristics
            if item.source.startswith("description:")
        }
        missing = [field for field in missing if field not in resolved]
        if draft.additional_specs:
            missing = [field for field in missing if field != "specs"]
    missing.extend(f"specs.{name}: противоречие с description" for name in conflicts)
    if needs_data and not missing:
        missing.append("Уточните назначение и характеристики прибора.")
    title = draft.seo_title.strip() if draft and not needs_data else None
    description = draft.seo_description.strip() if draft and not needs_data else None
    queries = [query.strip() for query in draft.search_queries] if draft and not needs_data else []
    return ProductCard(
        status="needs_data" if needs_data else "draft",
        product_name=product.name or "данных нет",
        manufacturer=product.manufacturer or "данных нет",
        seo_title=title,
        seo_description=description,
        characteristics=characteristics,
        search_queries=queries,
        commercial=draft.commercial.strip() if draft and not needs_data else None,
        missing_fields=list(dict.fromkeys(missing)),
        warnings=[
            "Черновик: перед публикацией сверьте смысл утверждений с исходными данными.",
            *warnings,
            *(
                ["Данных недостаточно или они противоречивы; SEO-карточка не сформирована."]
                if needs_data
                else []
            ),
        ],
        evidence=draft.evidence.model_dump() if draft and not needs_data else {},
        validation={
            "title_chars": len(title or ""),
            "description_chars": len(description or ""),
            "query_count": len(queries),
            "requirements_passed": not needs_data,
        },
        model=provider.model if attempts else None,
        generation_attempts=attempts,
    )


def generate_card(product: ProductInput, provider: Provider) -> ProductCard:
    suspicious = re.search(
        r"ignore.{0,60}(?:instructions|rules)|игнориру\w*.{0,60}(?:инструкц|правил)",
        "\n".join(product.sources().values()),
        re.IGNORECASE,
    )
    if suspicious:
        return _card(
            product,
            provider,
            warnings=[
                "В исходных данных обнаружен текст инструкций; проверьте его вручную.",
            ],
        )
    if not product.name or (not product.description and not any(product.specs.values())):
        return _card(product, provider)

    errors = []
    for attempt in (1, 2):
        try:
            draft = provider.generate(product, repair_errors=errors)
        except ModelOutputError:
            errors = ["invalid_response_structure"]
            continue
        errors = validate_draft(product, draft)
        if errors:
            continue
        conflicts = verified_conflicts(product, draft)
        return _card(product, provider, draft, attempt, conflicts)
    raise ModelOutputError(
        "Карточка не прошла проверки после двух попыток. "
        "Проверьте полноту и непротиворечивость исходных данных. Коды: " + ", ".join(errors)
    )
