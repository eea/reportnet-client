# Contributing

## Setup

```bash
uv sync
```

## Checks

```bash
uv run pytest                  # unit tests, no network
uv run pytest --integration    # live API; needs stored credentials
uv run ruff check src tests
uv run mypy src
```

## Documentation

`docs/` is written **for reporters** — people who submit data to Reportnet and
may be new to it. Keep it plain, short, and task-shaped. Library internals, API
quirks and design rationale do not belong there.

```bash
uv run mkdocs serve
```

Those internals live in `notes/` instead:

| File | What it holds |
|---|---|
| `notes/api-notes.md` | Reportnet API behaviour that is undocumented or contradicts the Swagger spec |
| `notes/live-tests-2003.md` | Measured results from live runs |

`AGENTS.md` is the guide for coding agents working in this repository, and is
the place for conventions and hard-won gotchas.

## Notebooks

```bash
uv sync --group explore
uv run marimo edit notebooks/01_reporter_workflow.py
```

Illustrations are generated, not hand-made — `python notebooks/images/make_images.py`.

## Releasing

Changes go in [CHANGELOG.md](CHANGELOG.md). Before 1.0, breaking changes may
occur in minor releases and are listed with migration notes.
