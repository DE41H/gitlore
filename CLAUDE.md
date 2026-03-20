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
| `Series` | `name`, `synopsis`, `author`, `visibility`, `spin_off` (self-FK), `spin_off_chapter` (FK→Chapter), `like_count`, `view_count`, `likes` (M2M) | `spin_off` → source series; `spin_off_chapter` → exact branching chapter |
| `Chapter` | `name`, `prompt`, `content`, `status`, `series` (→Series), `parent` (self-FK), `canon`, `embedding` | Tree node; `canon=True` marks the canonical lineage; `status` tracks generation state |
| `World` | `description`, `series` (OneToOne reverse), `embedding` | One per series via `Series.world` |
| `Character` | `name`, `description`, `series`, `embedding` | Many per series |
| `Genre` | `name`, `series` (M2M) | Shared across series |

`ChapterStatus` choices: `pending` · `generating` · `done` · `failed`

### Canon Chapter Rules
- One root canon chapter per series (`parent=NULL, canon=True`) — `unique_canon_root_per_series`
- At most one canon child per parent — `unique_canon_child_per_parent`
- A canon chapter's parent must also be canon — enforced in `Chapter.clean()` and `Chapter.toggle_canon()`
- A chapter must have `status=done` to be canon — DB constraint `canon_chapter_must_be_done`; also enforced in `clean()` and `toggle_canon()`

### Known Issues
- `like_count` is a denormalized counter; it drifts if `likes` M2M is modified outside `toggle_like`
- `toggle_canon` and `clean()` duplicate the same canon validation — must be kept in sync manually

### Key Methods
- `Series.copy(author, source_pk, chapter_pk=None, is_spin_off=False)` — classmethod; copies series with world, characters, genres atomically; `chapter_pk` required when `is_spin_off=True`
- `Series.toggle_like(user)` — atomic; uses `select_for_update()` + `F()` expressions
- `Series.add_view()` — single `UPDATE` with `F()`; refreshes `view_count` on instance
- `Chapter.start_spin_off(user)` — validates all lineage chapters are `DONE`, copies series, bulk-creates canon chapters root-first with `status=DONE`
- `Chapter.toggle_canon()` — atomic; enforces `status=DONE`, canon parent, unique-root, and unique-sibling constraints
- `Chapter.change_parent(new_parent_id)` — blocks cycles via `get_lineage()`; refuses if chapter is canon
- `Chapter.remove()` — re-parents children to grandparent; refuses if chapter is canon
- `Chapter.get_lineage(fields=None)` — recursive CTE walking parent chain upward; returns list from root to self
- `Chapter.get_descendants(fields=None)` — recursive CTE walking downward; returns all descendants including self in BFS order

### Embeddings
- `EMBEDDING_DIMENSIONS = 1536`
- `Character`, `World`, `Chapter` all have `VectorField` with HNSW indexes (`vector_cosine_ops`, m=16, ef_construction=64)
- Semantic search retrieves top-K relevant chapters as Claude context
- Chunking not yet implemented (`# - IMPLEMENT CHUNKING` in models.py)

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
