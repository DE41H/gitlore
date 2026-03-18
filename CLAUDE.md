# CLAUDE.md

GITLORE is a collaborative AI storytelling platform applying version control concepts (forks, spin-offs, likes) to creative fiction. Users write prompts, Claude generates story segments, others fork/spin-off from any chapter.

**Stack:** Python 3.14.3 · Django 6.0.3 · PostgreSQL + pgvector · Anthropic Claude API · Celery + Redis · Docker + Nginx · Stripe
**Frontend:** Django Templates (SSR) · HTMX · Tailwind CSS · `uv` for packages

## Layout

```
config/      # Django project: settings, urls, wsgi, asgi, celery
series/      # Main app: models, views, admin, tests
templates/   # SSR templates
```

Only `series` is a registered app. `config/` is the project root, not an app.
DB table prefix: `series_`. Use `Model._meta.db_table` in raw SQL — never hardcode.

## Commands

```bash
uv sync
uv run python manage.py runserver
uv run python manage.py test
uv run python manage.py test series.tests.ClassName.method
uv run python manage.py makemigrations && uv run python manage.py migrate
```

## Data Model (`series/models.py`)

| Model | Key fields | Notes |
|-------|-----------|-------|
| `Series` | `name`, `synopsis`, `author`, `visibility`, `spin_off` (self-FK), `like_count`, `likes` (M2M) | `spin_off` → original series this was forked from |
| `Chapter` | `name`, `prompt`, `content`, `series` (→Series), `parent` (self-FK), `canon`, `embedding` | Tree node; `canon=True` marks the canonical lineage |
| `World` | `description`, `series` (OneToOne), `embedding` | One per series |
| `Character` | `name`, `description`, `series`, `embedding` | Many per series |
| `Genre` | `name`, `series` (M2M) | Shared across series |

### Canon Chapter Rules
- One root canon chapter per series (`parent=NULL, canon=True`) — `unique_canon_series_per_series`
- At most one canon child per parent — `unique_canon_child_per_parent`
- A canon chapter's parent must also be canon — **not yet enforced** (`Chapter.clean()` missing)

### Key Methods
- `Series.toggle_like(user)` — atomic; uses `select_for_update()` + `F()` expressions
- `Series.create_copy(source_pk, author, is_spin_off=False)` — copies series with world, characters, genres
- `Chapter.create_spin_off(user)` — calls `create_copy`, walks parent chain in Python, `bulk_create` + `bulk_update` canon chapters in root-first order

### Embeddings
- `EMBEDDING_DIMENSIONS = 1536`
- `Character`, `World`, `Chapter` all have `VectorField` with HNSW indexes (`vector_cosine_ops`, m=16, ef_construction=64)
- Semantic search retrieves top-K relevant chapters as Claude context

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `"true"` to enable debug |
| `DJANGO_ALLOWED_HOSTS` | Space-separated |
| `DATABASE_ENGINE` | e.g. `django.db.backends.postgresql` |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | DB connection |
| `CELERY_BROKER_URL` | Redis URL |

## Architecture Notes

- **Async tasks:** Celery + Redis; `CELERY_TASK_TIME_LIMIT=300s`. Story generation runs as Celery tasks
- **Credit system:** Per-user prompt token quota; Stripe paid tiers bypass limits
- **Frontend:** HTMX for story generation streaming and fork/spin-off without page reloads
- **Export targets:** Wattpad and Webtoon (Phase 4, not yet implemented)
- **Timezone:** `Asia/Kolkata`
