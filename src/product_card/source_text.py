import re


def commercial_options(description: str | None) -> list[str]:
    """Offer short source excerpts, avoiding invented audiences and technical promises."""
    if not description:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[А-ЯA-Z])", description.strip())
    quantified = re.compile(r"\d\s*(?:[°%]|(?:мм|mm|кг|kg|г|g|в|v|с|s|мин|ч|h)\b)", re.I)
    excluded = re.compile(r"погрешност|точност|не подтвержд|не относят", re.I)
    safe = [
        s.strip()
        for s in sentences
        if s.strip() and len(s) <= 450 and not quantified.search(s) and not excluded.search(s)
    ]
    if not safe:
        return []
    options = [safe[0]]
    options.extend(
        f"{safe[0]} {sentence}" for sentence in safe[1:4] if len(safe[0]) + len(sentence) + 1 <= 600
    )
    return list(dict.fromkeys(options))
