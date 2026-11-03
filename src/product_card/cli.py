import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from groq import Groq

from product_card.errors import AppError, InputError
from product_card.models import MAX_INPUT_BYTES, parse_product
from product_card.ollama_provider import OllamaProvider
from product_card.provider import GroqProvider
from product_card.render import render_markdown
from product_card.service import generate_card


def _targets(output_format: str, output: str | None) -> list[Path]:
    if output_format == "both":
        if not output:
            raise InputError("Для --format both укажите --output с префиксом файлов.")
        return [Path(output + ".json"), Path(output + ".md")]
    return [Path(output)] if output else []


def _write_exclusive(targets: list[Path], contents: list[str]):
    created = []
    try:
        for path, content in zip(targets, contents, strict=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(content)
    except OSError:
        # Roll back only files created by this operation, never an existing user file.
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Черновик B2B-карточки товара через LLM API.")
    parser.add_argument("input", help="Путь к UTF-8 JSON одного товара")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="json")
    parser.add_argument("--output", help="Файл вывода; для both префикс без расширения")
    args = parser.parse_args(argv)

    try:
        path = Path(args.input)
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise InputError("Превышен допустимый размер входного файла: 256 КиБ.")
        product = parse_product(path.read_text(encoding="utf-8-sig"))
        targets = _targets(args.format, args.output)
        if any(target.exists() for target in targets):
            raise InputError("Файл результата уже существует. Укажите другое имя для сохранения.")
        load_dotenv(Path.cwd() / ".env", override=False)
        selected = os.environ.get("PRODUCT_CARD_PROVIDER", "groq").strip().lower()
        if selected == "ollama":
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
            model = os.environ.get("OLLAMA_MODEL", "qwen3-coder:30b").strip()
            if not model:
                raise InputError("OLLAMA_MODEL не должен быть пустым.")
            with httpx.Client(timeout=240.0, trust_env=False) as client:
                card = generate_card(product, OllamaProvider(client, base_url, model))
        elif selected == "groq":
            key = os.environ.get("GROQ_API_KEY", "").strip()
            model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
            if not model:
                raise InputError("GROQ_MODEL не должен быть пустым.")
            if key:
                with Groq(
                    api_key=key,
                    base_url="https://api.groq.com",
                    timeout=30.0,
                    max_retries=1,
                ) as client:
                    card = generate_card(product, GroqProvider(client, model))
            else:
                card = generate_card(product, GroqProvider(None, model))
        else:
            raise InputError("PRODUCT_CARD_PROVIDER должен быть groq или ollama.")
        json_text = (
            json.dumps(card.model_dump(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        markdown = render_markdown(card)
        contents = (
            [json_text, markdown]
            if args.format == "both"
            else [
                markdown if args.format == "markdown" else json_text,
            ]
        )
        if targets:
            _write_exclusive(targets, contents)
            print(
                "Результат сохранён: " + ", ".join(str(target) for target in targets),
                file=sys.stderr,
            )
        else:
            sys.stdout.write(contents[0])
        return 0 if card.status == "draft" else 4
    except AppError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, UnicodeError):
        print(
            "Ошибка: не удалось прочитать вход или сохранить результат. "
            "Проверьте путь, права доступа и кодировку UTF-8.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
