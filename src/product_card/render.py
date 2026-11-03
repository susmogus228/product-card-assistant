import html
import re

from product_card.models import ProductCard


def _text(value: str) -> str:
    escaped = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]#+!])", r"\\\1", escaped)


def _cell(value: str) -> str:
    return _text(value).replace("|", r"\|").replace("\r\n", "\n").replace("\n", "<br>")


def render_markdown(card: ProductCard) -> str:
    state = "Черновик" if card.status == "draft" else "Нужны уточнения"
    lines = [
        f"# {_text(card.product_name)}",
        "",
        f"Статус: {state}",
        "",
        f"Производитель: {_text(card.manufacturer)}",
        "",
        "## SEO-заголовок",
        "",
        _text(card.seo_title or "данных недостаточно"),
        "",
        "## SEO-описание",
        "",
        _text(card.seo_description or "данных недостаточно"),
        "",
        "## Ключевые характеристики",
        "",
        "| Характеристика | Значение | Источник |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {_cell(item.name)} | {_cell(item.value)} | {_cell(item.source)} |"
        for item in card.characteristics
    )
    lines.extend(["", "## Поисковые запросы", ""])
    lines.extend(f"- {_text(query)}" for query in card.search_queries)
    if not card.search_queries:
        lines.append("данных недостаточно")
    lines.extend(
        [
            "",
            "## Для менеджера",
            "",
            _text(card.commercial or "данных недостаточно"),
            "",
            "## Что уточнить",
            "",
        ]
    )
    lines.extend(
        f"- {_text(field)}: данных нет или требуется уточнение." for field in card.missing_fields
    )
    if not card.missing_fields:
        lines.append("Пропуски во входных полях не обнаружены.")
    lines.extend(
        [
            "",
            "## Проверки",
            "",
            f"Заголовок: {card.validation['title_chars']} символов. "
            f"Описание: {card.validation['description_chars']} символов. "
            f"Запросы: {card.validation['query_count']}.",
            "",
        ]
    )
    lines.extend(f"- {_text(warning)}" for warning in card.warnings)
    return "\n".join(lines) + "\n"
