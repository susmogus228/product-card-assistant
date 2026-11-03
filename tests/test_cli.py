import json

import pytest
from test_generation import SequenceProvider

from product_card.cli import main
from product_card.errors import ProviderError
from product_card.render import render_markdown
from product_card.service import generate_card


def test_markdown_escapes_table_cells(sample_product, valid_draft):
    sample_product.specs["примечание"] = "A | B\nC"
    card = generate_card(sample_product, SequenceProvider(valid_draft))
    text = render_markdown(card)
    assert "A \\| B<br>C" in text
    assert "SEO-описание" in text


@pytest.fixture
def input_file(tmp_path, sample_product):
    path = tmp_path / "product.json"
    path.write_text(sample_product.model_dump_json(), encoding="utf-8")
    return path


def test_cli_invalid_json_has_safe_error_and_no_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "bad.json"
    path.write_text('{"name":', encoding="utf-8")
    assert main([str(path), "--output", "card.json"]) == 2
    assert not (tmp_path / "card.json").exists()
    assert "Traceback" not in capsys.readouterr().err


def test_cli_missing_key_is_actionable(input_file, monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main([str(input_file)]) == 2
    assert "GROQ_API_KEY" in capsys.readouterr().err


def test_cli_preserves_existing_output_without_api(input_file, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "card.json"
    output.write_text("USER_CONTENT", encoding="utf-8")
    assert main([str(input_file), "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "USER_CONTENT"


def test_cli_exports_both_formats_from_one_generation(
    input_file,
    monkeypatch,
    tmp_path,
    valid_draft,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "local-test-key")
    monkeypatch.setattr("product_card.provider.GroqProvider.generate", lambda *a, **k: valid_draft)
    assert main([str(input_file), "--format", "both", "--output", "card"]) == 0
    data = json.loads((tmp_path / "card.json").read_text(encoding="utf-8"))
    assert data["status"] == "draft"
    assert data["validation"]["description_chars"] == 951
    assert "Термометр Testo" in (tmp_path / "card.md").read_text(encoding="utf-8")


def test_cli_failed_api_does_not_create_output(input_file, monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "local-test-key")

    def fail(*args, **kwargs):
        raise ProviderError("Достигнут лимит Groq.")

    monkeypatch.setattr("product_card.provider.GroqProvider.generate", fail)
    assert main([str(input_file), "--output", "card.json"]) == 3
    assert not (tmp_path / "card.json").exists()
    assert "Traceback" not in capsys.readouterr().err


def test_cli_needs_data_has_distinct_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "local-test-key")
    path = tmp_path / "empty.json"
    path.write_text("{}", encoding="utf-8")
    assert main([str(path)]) == 4
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "needs_data"
    assert data["generation_attempts"] == 0


def test_both_formats_preserve_existing_markdown(input_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "card.md").write_text("USER_CONTENT", encoding="utf-8")
    assert main([str(input_file), "--format", "both", "--output", "card"]) == 2
    assert not (tmp_path / "card.json").exists()


def test_missing_input_is_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["missing.json"]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_empty_product_does_not_require_api_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    path = tmp_path / "empty.json"
    path.write_text("{}", encoding="utf-8")
    assert main([str(path)]) == 4
    assert json.loads(capsys.readouterr().out)["generation_attempts"] == 0


def test_cli_uses_ollama_when_selected(input_file, monkeypatch, tmp_path, valid_draft):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRODUCT_CARD_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(
        "product_card.ollama_provider.OllamaProvider.generate", lambda *a, **k: valid_draft
    )
    assert main([str(input_file), "--output", "card.json"]) == 0
    data = json.loads((tmp_path / "card.json").read_text(encoding="utf-8"))
    assert data["model"] == "test-model"


def test_cli_rejects_unknown_provider(input_file, monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRODUCT_CARD_PROVIDER", "unknown")
    assert main([str(input_file)]) == 2
    assert "PRODUCT_CARD_PROVIDER" in capsys.readouterr().err
