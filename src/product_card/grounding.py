import re
import unicodedata

from product_card.models import Draft, ProductInput, normalize_spec_name
from product_card.source_text import commercial_options

NUMBER = r"[-+]?\d+(?:[.,]\d+)?"
UNIT = (
    r"(?:°\s*[cсfф]|%\s*(?:rh|rн|ов)?|мпа|кпа|па|mpa|kpa|bar|бар|мм|mm|"
    r"мв|мa|ма|в|v|гц|hz|кг|kg|г|g|мс|мл|ml|с|ч)"
)
MEASUREMENT = re.compile(rf"(?:(?<!\w)|(?=[+-]))({NUMBER})\s*({UNIT})(?![\w])", re.IGNORECASE)
RANGE = re.compile(
    rf"({NUMBER})\s*(?:до|to|[–—…]|\.\.\.|-)\s*({NUMBER})\s*({UNIT})(?![\w])",
    re.IGNORECASE,
)
# Scan numeric components even in identifiers or unrecognised units; signed known
# measurements are checked separately, so model names cannot bypass the numeric guard.
NUMBERS = re.compile(r"\d+(?:[.,]\d+)?")
BATTERY_COUNT = re.compile(r"\b(\d+)\s*(?:(?:батаре\w*|элемент\w*)\s+)?(AAA|AA)\b", re.IGNORECASE)
TECHNICAL_TERMS = [
    r"bluetooth",
    r"wi[ -]?fi",
    r"rs[ -]?485",
    r"modbus",
    r"usb",
    r"atex",
    r"ip\s*\d{2}",
    r"нержавеющ\w*",
    r"взрывозащи\w*",
    r"водонепроница\w*",
    r"кислотостой\w*",
    r"искробезопас\w*",
    r"сертифицир\w*",
    r"поверен\w*",
    r"погружать\s+(?:прибор\w*|устройств\w*|корпус\w*)",
]
USE_CASE_TERMS = [r"производств\w*", r"медицин\w*", r"больниц\w*", r"нефтегаз\w*"]
QUALITY_TERMS = [r"высок\w*\s+точност\w*"]


def _canonical_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace(",", ".")
    return value.translate(str.maketrans({char: "-" for char in "‐‑‒–—−"}))


def _normalized(text: str) -> str:
    return _canonical_text(text).casefold()


def _number(text: str) -> str:
    return text.replace(",", ".").lstrip("+")


def _unit(unit: str) -> str:
    unit = re.sub(r"\s", "", unit)
    aliases = {
        "mm": "мм",
        "kg": "кг",
        "g": "г",
        "V": "В",
        "v": "В",
        "MPa": "МПа",
        "mPa": "мПа",
        "kPa": "кПа",
        "Pa": "Па",
        "mV": "мВ",
        "°С": "°C",
        "°c": "°C",
        "°с": "°C",
    }
    return aliases.get(unit, unit)


def _battery_pairs(text: str) -> set[tuple[int, str]]:
    return {(int(number), kind.upper()) for number, kind in BATTERY_COUNT.findall(text)}


def _measurements(text: str) -> set[tuple[str, str]]:
    text = _canonical_text(text)
    result = set()
    for match in MEASUREMENT.finditer(text):
        value, unit = match.groups()
        if value.startswith("-") and match.start() and text[match.start() - 1].isdigit():
            value = value[1:]
        result.add((_number(value), _unit(unit)))
    for low, high, unit in RANGE.findall(text):
        result.add((_number(low), _unit(unit)))
        result.add((_number(high), _unit(unit)))
    return result


def verified_conflicts(product: ProductInput, draft: Draft) -> list[str]:
    result = []
    description = product.description or ""
    for conflict in draft.conflicts:
        current = product.specs.get(conflict.spec_name)
        if (
            current
            and conflict.source_quote in description
            and conflict.description_value in conflict.source_quote
            and _normalized(current) != _normalized(conflict.description_value)
        ):
            result.append(conflict.spec_name)
    return result


def validate_draft(product: ProductInput, draft: Draft) -> list[str]:
    errors = []
    if not draft.insufficient_data:
        if not 1 <= len(draft.seo_title.strip()) <= 70:
            errors.append("seo_title_length")
        if not 800 <= len(draft.seo_description.strip()) <= 1200:
            errors.append("seo_description_length")
        if not 3 <= len(draft.search_queries) <= 5 or any(
            not query.strip() or len(query) > 160 for query in draft.search_queries
        ):
            errors.append("search_queries_count_or_length")
        if not 1 <= len(draft.commercial.strip()) <= 600:
            errors.append("commercial_length")
        queries = {_normalized(query.strip()) for query in draft.search_queries}
        if len(queries) != len(draft.search_queries):
            errors.append("search_queries_not_unique")

    source_map = product.sources()
    for field, refs in draft.evidence.model_dump().items():
        if (getattr(draft, field) and not refs) or any(ref not in source_map for ref in refs):
            errors.append("invalid_source_reference")

    description = product.description or ""
    known_names = {normalize_spec_name(key): value for key, value in product.specs.items()}
    for spec in draft.additional_specs:
        if (
            spec.source_quote not in description
            or spec.value not in spec.source_quote
            or normalize_spec_name(spec.name) not in normalize_spec_name(spec.source_quote)
        ):
            errors.append("unverified_additional_spec")
        name = normalize_spec_name(spec.name)
        if name in known_names and known_names[name] is not None:
            if _normalized(known_names[name]) != _normalized(spec.value):
                errors.append("conflicting_spec")
        known_names[name] = spec.value

    if len(verified_conflicts(product, draft)) != len(draft.conflicts):
        errors.append("unverified_conflict")

    raw_source = "\n".join(source_map.values())
    source = _normalized(raw_source)
    commercial = _normalized(draft.commercial)
    if MEASUREMENT.search(commercial) or re.search(r"погрешност|точност", commercial):
        errors.append("commercial_technical_details")
    options = commercial_options(product.description)
    if options and not draft.insufficient_data and draft.commercial not in options:
        errors.append("commercial_not_source_excerpt")
    raw_text = "\n".join(
        [
            draft.seo_title,
            draft.seo_description,
            draft.commercial,
            *draft.search_queries,
        ]
    )
    text = _normalized(raw_text)
    allowed_numbers = {_number(value) for value in NUMBERS.findall(source)}
    if {_number(value) for value in NUMBERS.findall(text)} - allowed_numbers:
        errors.append("unsupported_numeric_value")
    if _measurements(raw_text) - _measurements(raw_source):
        errors.append("unsupported_measurement")
    if _battery_pairs(raw_text) - _battery_pairs(raw_source):
        errors.append("unsupported_battery_count")
    for term in TECHNICAL_TERMS:
        if re.search(term, text) and not re.search(term, source):
            errors.append("unsupported_technical_claim")
            break
    if any(re.search(term, text) and not re.search(term, source) for term in QUALITY_TERMS):
        errors.append("unsupported_quality_claim")
    # Manufacturer attribution is not evidence of an industrial use case.
    manufacturer = _normalized(product.manufacturer or "").split()
    if manufacturer and len(manufacturer[0]) >= 3:
        attribution = rf"\bпроизводства\s+{re.escape(manufacturer[0])}(?!\w)"
        use_case_text = re.sub(attribution, "", text)
        use_case_source = re.sub(attribution, "", source)
    else:
        use_case_text, use_case_source = text, source
    if any(
        re.search(term, use_case_text) and not re.search(term, use_case_source)
        for term in USE_CASE_TERMS
    ):
        errors.append("unsupported_use_case")
    return list(dict.fromkeys(errors))
