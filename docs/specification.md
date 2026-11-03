# Product card assistant: agreed specification

Source: employer PDF, sections 1-9, read on 2026-11-03. The PDF has three pages,
one sample JSON, and no embedded product attachments. The employer's two inputs
are pending. The user authorized two complete independently sourced demo products
and several negative examples while waiting for the employer.

## Scope

Python 3.12 CLI, one Groq model, JSON file input and JSON/Markdown output. No web UI,
database, CMS, deployment, model fine-tuning, Git push or remote publication.
Root owns implementation; a read-only requirements-auditor reviews the integration.
Root path: D:\Projects\product-card-assistant. Scratch: work/. Results: outputs/.

## Acceptance

1. Accept the input shape name, manufacturer, specs, description. Reject malformed
   JSON, duplicate keys, invalid types and oversized inputs with clear Russian errors.
2. Submit the input to a real LLM API; keep the API key in ignored local .env.
3. Produce an SEO title of 1-70 Unicode characters, SEO description of 800-1200
   Unicode characters including spaces, structured characteristics, 3-5 distinct
   search queries and a short commercial block. Output is a draft for human review.
4. Copy given specs verbatim. Additional specs from description require a literal
   source quote containing the value. Conflicts require clarification; do not silently
   choose one value. Do not invent technical data, suitability, stock or certification.
5. Mark empty fields with "данных нет" and list needed clarifications. When the input
   cannot support a complete draft, return needs_data and do not claim length compliance.
6. Use a strict provider schema plus local validation. Source references and lexical
   guards support grounding; they do not prove semantic entailment. Manually reconcile
   the two final demo outputs against their official inputs.
7. Handle missing/invalid keys, 429, timeout, network/provider errors, refusal, truncated
   responses and invalid model outputs. Bound network retries and one corrective generation.
8. Ship source, pinned dependencies, README, prompts, two input/output demo pairs,
   negative inputs, tests, limitations and a submission message template.
9. Clearly distinguish demo products from the employer-provided products. A real
   repository URL remains pending until the user authorizes Git publication.

## Memory and agents

- Codex memory: no relevant prior implementation found; rely on the employer PDF.
- Codebase Memory: fresh list_projects has no entry for this new project. No indexing.
- Workstreams: contracts/grounding -> provider/service -> CLI/docs/live verification.
- Workers: root implements the shared source surface; no independent worker needed.
- Reviewer: requirements-auditor, read-only PDF/spec/code/tests/results reconciliation.
