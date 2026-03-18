# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

GITLORE is a collaborative AI storytelling platform applying version control concepts (forks, spin-offs, likes) to creative fiction. Users write prompts, Claude generates story segments, others fork/spin-off from any chapter.

**Stack:** Python 3.14.3 · Django 6.0.3 · PostgreSQL + pgvector · Anthropic Claude API · Celery + Redis · Docker + Nginx · Stripe
**Frontend:** Django Templates (SSR, `templates/`) · HTMX · Tailwind CSS
**Package manager:** `uv`

## Project Layout

```
config/          # Django project: settings, urls, wsgi, asgi, celery
series/          # Main app: models, views, admin, tests
templates/       # SSR templates (series/series_list.html, etc.)
manage.py
```

**Apps:** only `series` is registered. `config/` is the Django project root, not an app.
**DB table prefix:** `series_` (e.g. `series_chapter`, `series_series`). Use `Model._meta.db_table` in raw SQL — never hardcode.

## Commands

```bash
uv sync                                                    # install deps
uv run python manage.py runserver                          # dev server
uv run python manage.py test                               # all tests
uv run python manage.py test series.tests.ClassName.method # single test
uv run python manage.py makemigrations && uv run python manage.py migrate
```

## Data Model (`series/models.py`)

### Models
| Model | Key fields | Notes |
|-------|-----------|-------|
| `Series` | `name`, `author`, `description`, `visibility`, `spin_off` (self-FK), `like_count` | `spin_off` points to the original series this was forked from |
| `Chapter` | `name`, `prompt`, `root` (→Series), `parent` (self-FK), `stem`, `embedding` | Tree node; `stem=True` marks the canonical lineage |
| `World` | `description`, `series` (OneToOne), `embedding` | One world per series |
| `Character` | `name`, `description`, `series`, `embedding` | Many per series |
| `Genre` | `name`, `series` (M2M) | Shared across series |

### Stem Chapter Rules (enforced via constraints + `clean()`)
- A series has **exactly one** root stem chapter (`parent=NULL, stem=True`) — enforced by `unique_stem_root_per_series`
- Each stem chapter has **at most one** stem child — enforced by `unique_stem_child_per_parent`
- A stem chapter's parent must also be stem — enforced by `Chapter.clean()` (application-level); needs a DB trigger for bulk operations

### Key Methods
- `Series.like(user)` / `Series.unlike(user)` — atomic, uses `select_for_update` + `F()` expressions to prevent race conditions
- `Series.create_copy(author, spin_off=None)` — copies series with world, characters, genres; handles name collisions via savepoint retry loop
- `Chapter.create_spin_off(user)` — creates a series copy, then uses a **recursive CTE** to fetch the chapter's lineage and `bulk_create` stem chapters in root-first order

### Embeddings
- `EMBEDDING_DIMENSIONS = 1536` (OpenAI text-embedding-ada-002)
- `Character`, `World`, `Chapter` all have `VectorField` with HNSW indexes (`vector_cosine_ops`, m=16, ef_construction=64)
- Semantic search retrieves top-K relevant chapters as Claude context — avoids passing full history

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `"true"` to enable debug |
| `DJANGO_ALLOWED_HOSTS` | Space-separated allowed hosts |
| `DATABASE_ENGINE` | e.g. `django.db.backends.postgresql` |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | DB connection |
| `CELERY_BROKER_URL` | Redis URL for Celery broker + result backend |

## Architecture Notes

- **Async tasks:** Celery with Redis; `CELERY_TASK_TIME_LIMIT=300s`. Story generation (Claude API calls) should run as Celery tasks
- **Credit system:** Per-user prompt token quota in Django; Stripe paid tiers bypass limits
- **Spin-off flow:** `Chapter.create_spin_off` → `Series.create_copy` (copies world/characters/genres) → recursive CTE lineage fetch → `bulk_create` + `bulk_update` parent chain
- **Frontend interactions:** HTMX for story generation streaming, fork/spin-off without page reloads
- **Export targets:** Wattpad and Webtoon (Phase 4, not yet implemented)
- **Timezone:** `Asia/Kolkata`
