# Notes for AI coding agents

Home Assistant custom integration (HACS) for inexogy smart meters.

## Read first

- [`docs/SPEC.md`](docs/SPEC.md) – specification and architecture, the source of truth.
  Requirement IDs (`REQ-…`, `NFR-…`, `ADR-…`) are referenced in code reviews and PRs.
- [`bruno/`](bruno) – one request per portal endpoint, with docs.

## Workflow (spec-driven)

1. Find or add the requirement in `docs/SPEC.md` for the change. Behaviour changes
   update the spec **in the same pull request**.
2. Implement. Keep `parser.py` and `stats.py` free of Home Assistant imports.
3. Add or adjust tests in `tests/` (synthetic data only).
4. New or changed endpoint → update `bruno/` (request + `docs` block + table in
   `bruno/README.md`) and SPEC §3.
5. User-visible change → update `README.md` and both translations (`en`, `de`, plus
   `strings.json`).
6. Bump `version` in `custom_components/inexogy/manifest.json` (semver).
7. Open a pull request; `main` is protected and requires the checks `hacs`, `hassfest`,
   `tests`.

## Commands

```bash
uvx ruff check . && uvx ruff format --check .
python3 -m pytest -q
```

## Hard rules

- **No personal data** in code, tests, docs, commits or PRs: no real meter serials,
  series/container IDs, tokens, emails, names, addresses, phone numbers. Use values like
  `00000000`, `1ABC0012345678`, `abc`, `user@example.com`.
- Never commit credentials. Bruno secrets are Bruno *secret* environment variables;
  never add files with credentials.
- Do not change unique IDs or device identifiers without a migration (SPEC REQ-14).
- Keep API load low (NFR-01): no extra calls per poll without a spec change.
- Do not push to `main` directly and do not create tags/releases unless asked.

## Conventions

- Match the existing style: typed Python 3.13, `from __future__ import annotations`,
  docstrings on public functions, ruff config in `pyproject.toml`.
- Entities use `has_entity_name` + `translation_key`; diagnostics use
  `EntityCategory.DIAGNOSTIC` and are disabled by default.
