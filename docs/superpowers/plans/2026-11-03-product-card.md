# Product Card Assistant Implementation Plan

> Execution: root implements inline; one read-only requirements-auditor reviews the result.

**Goal:** A locally runnable, source-grounded draft generator meeting the employer PDF.

**Architecture:** Validate JSON at the boundary, keep original specs authoritative,
generate copy through Groq strict JSON Schema, validate grounding and business limits,
then render JSON/Markdown. Separate provider failures from invalid model content.

**Tech Stack:** Python 3.12, Pydantic 2, Groq SDK, python-dotenv, pytest, ruff.

**Spec:** docs/specification.md

## Global constraints

- Title <=70 characters; description 800-1200 including spaces; 3-5 distinct queries.
- Technical values must come from the input; missing values use "данных нет".
- Secrets stay in .env and out of Git, logs, examples, artifacts and tests.
- Two current demo products are independently sourced, not employer-supplied inputs.
- No push, publication, global environment change or model fine-tuning.

## Review focus

- Wrong field types, duplicate JSON keys and NaN must fail before any API call.
- Missing facts and conflicting quoted values must produce clarification, not a guess.
- A model may copy an existing number with the wrong unit; unit/value guards must reject it.
- API and schema errors must not leak request/credential bodies.
- CLI failures must not replace existing output files or report a successful generation.

## Task 1: contracts and grounding

Files: src/product_card/models.py, grounding.py, errors.py; tests/test_contracts.py,
tests/test_grounding.py. Interfaces: parse_product(raw: str) -> ProductInput;
validate_draft(product: ProductInput, draft: Draft) -> list[str].

- [x] Write tests for strict input types, whitespace/missing values, malformed JSON,
  duplicate keys, and valid/invalid grounding and exact length boundaries.
- [x] Run focused tests and observe missing implementation failure.
- [x] Implement schemas, parsing, source quotes, conflict detection and lexical guards.
- [x] Run the task suite; expected all pass.

## Task 2: Groq provider and generation service

Files: provider.py, service.py, prompts.py; tests/test_generation.py, test_provider.py.
Consumes ProductInput/Draft and validate_draft. Produces generate_card(product,
provider) -> ProductCard and GroqProvider.generate(product, repair_errors) -> Draft.

- [x] Write tests for real SDK calls using httpx MockTransport at the network boundary,
  API errors, empty/truncated/refusal responses, one correction and insufficient data.
- [x] Run focused tests and observe missing implementation failure.
- [x] Implement one provider, grounded prompt with examples, bounded retries,
  draft/needs_data status and programmatic characteristic assembly.
- [x] Run the whole suite; expected all pass.

## Task 3: CLI, examples and acceptance evidence

Files: cli.py, __main__.py, render.py; examples/, README.md, docs/, outputs/;
tests/test_cli.py. Consumes generation service; produces product-card command.

- [x] Write tests for JSON/Markdown rendering, invalid files, no key, failed provider,
  no output overwrite, source facts and Unicode lengths.
- [x] Run focused tests and observe missing implementation failure.
- [x] Implement CLI and readable export. Source two complete Testo demo products from
  the manufacturer's product pages/datasheets. Record sources and negative examples.
- [x] Run tests and ruff; run real Groq generation for both products; manually reconcile
  values and claims; retry only after an observed fault.
- [x] Verify installation and README commands in a clean venv. Package secret-free
  deliverables in the chat outputs directory. Verify archive contents and SHA256.
- [x] Obtain requirements-auditor verdict and fix material findings with regression tests.
