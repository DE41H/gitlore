# CLAUDE.md

GITLORE is a collaborative AI storytelling platform applying version control concepts (forks, spin-offs, likes) to creative fiction. Users write prompts, Gemini generates story segments, others fork/spin-off from any chapter.

**Stack:** Python 3.14.3 · Django 6.0.3 · PostgreSQL + pgvector · Google Gemini API · Celery + Redis · Docker + Nginx · Stripe
**Frontend:** Django Templates (SSR) · HTMX · Tailwind CSS · `uv` for packages

## Layout

```
config/               # Django project: settings, urls, wsgi, asgi, celery
series/               # Main app (only registered app)
  models/             # One file per model
  services/           # Business logic: canon, tree, authoring, social, text
  ai/                 # AI layer: gemini client, embedding, generation
  tasks.py            # Celery tasks (create_embeddings, generate_chapter)
  signals.py          # Django signals
  views.py / admin.py / tests.py
templates/            # SSR templates
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

## Data Model (`series/models/`)

| Model | Key fields | Notes |
|-------|-----------|-------|
| `Series` | `name`, `synopsis`, `author`, `visibility`, `spin_off` (self-FK), `spin_off_chapter` (FK→Chapter), `like_count`, `view_count`, `likes` (M2M), `world` (OneToOne→World), `genres` (M2M) | `spin_off` → source series; `spin_off_chapter` → exact branching chapter |
| `Chapter` | `name`, `prompt`, `content`, `status`, `series` (→Series), `parent` (self-FK), `canon` | Tree node; `canon=True` marks the canonical lineage; `status` tracks generation state |
| `World` | `description` | One per series via `Series.world` (reverse: `world.series`) |
| `Character` | `name`, `description`, `series` | Many per series |
| `Genre` | `name`, `series` (M2M) | Shared across series |

`ChapterStatus` choices: `pending` · `generating` · `done` · `failed`

### Chunk Models (Embeddings)
Embeddings are stored in separate chunk models, not on the main models directly:

| Model | Fields | Notes |
|-------|--------|-------|
| `WorldChunk` | `embedding` (VectorField), `world` (FK) | Chunked world description embeddings |
| `CharacterChunk` | `embedding` (VectorField), `character` (FK) | Chunked character description embeddings |
| `ChapterChunk` | `embedding` (VectorField), `chapter` (FK) | Chunked chapter content embeddings |

`EMBEDDING_DIMENSIONS = 1536` (defined in `settings.py`). All chunk models use HNSW indexes (`vector_cosine_ops`, m=16, ef_construction=64).

### Canon Chapter Rules
- One root canon chapter per series (`parent=NULL, canon=True`) — `unique_canon_root_per_series`
- At most one canon child per parent — `unique_canon_child_per_parent`
- A canon chapter's parent must also be canon — enforced in `services/canon.py:toggle_canon()`
- A chapter must have `status=done` to be canon — DB constraint `canon_chapter_must_be_done`; also enforced in `toggle_canon()`

### Known Issues
- `like_count` is a denormalized counter; it drifts if `likes` M2M is modified outside `services/social.py:toggle_like()`
- `start_spin_off` uses `get_lineage()` without `fields`, fetching `SELECT *` via raw SQL — mutates those raw instances in-place before `bulk_create`; relies on `bulk_create` preserving insertion order to re-link parents

## Services (`series/services/`)

Business logic lives here, not on models.

| Module | Functions | Notes |
|--------|-----------|-------|
| `canon.py` | `toggle_canon(chapter_id)` | Atomic; enforces `status=DONE`, canon parent, unique-root, unique-sibling |
| `social.py` | `toggle_like(series_id, user_id)`, `add_view(series_id)` | `toggle_like` uses `select_for_update()` + `F()`; `add_view` is a single `UPDATE` |
| `authoring.py` | `replicate(series_id, author_id, spin_off_chapter_id=None)`, `start_spin_off(chapter_id, author_id)` | `replicate` copies series with world/characters/genres atomically; `start_spin_off` validates lineage, replicates, bulk-creates canon chapters root-first |
| `tree.py` | `get_lineage(chapter_id, fields=None)`, `get_descendants(chapter_id, fields=None)`, `change_parent(chapter_id, new_parent_id)` | CTEs; `get_lineage` returns root→self; `get_descendants` returns BFS order; `change_parent` blocks cycles and refuses canon chapters |
| `text.py` | `split_text(text)` | LangChain `RecursiveCharacterTextSplitter` with tiktoken (gpt2), chunk_size=1000, overlap=200 |

## AI Layer (`series/ai/`)

| Module | Contents | Notes |
|--------|----------|-------|
| `gemini.py` | `client`, `generation_model`, `embedding_model` | Singleton Gemini client; `generation_model = "gemini-2.5-flash"`, `embedding_model = "text-embedding-004"` |
| `embedding.py` | `get_embeddings(text_list, task_type)`, `embed_world(world_id)`, `embed_character(character_id)`, `embed_series(series_id)` | Batched at 100; `embed_series` batches world + all characters in a single API call |
| `generation.py` | `generate_chapter_content(chapter_id)` | Builds system prompt (world + characters) + user message (lineage + prompt); updates chapter `status` through `generating`→`done`/`failed` |

## Celery Tasks (`series/tasks.py`)

| Task | Args | Notes |
|------|------|-------|
| `create_series_embeddings` | `series_id` | Calls `embed_series(series_id)` |
| `create_world_embeddings` | `world_id` | Calls `embed_world(world_id)` |
| `create_character_embeddings` | `character_id` | Calls `embed_character(character_id)` |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `"true"` to enable debug |
| `DJANGO_ALLOWED_HOSTS` | Space-separated |
| `DATABASE_ENGINE` | e.g. `django.db.backends.postgresql` |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | DB connection |
| `CELERY_BROKER_URL` | Redis URL (also used as cache backend) |
| `GOOGLE_API_KEY` | Gemini API key |

## Architecture Notes

- **Async tasks:** Celery + Redis; `CELERY_TASK_TIME_LIMIT=300s`. Story generation runs as Celery tasks
- **Credit system:** Per-user prompt token quota; Stripe paid tiers bypass limits
- **Frontend:** HTMX for story generation and fork/spin-off without page reloads
- **Export targets:** Wattpad and Webtoon (Phase 4, not yet implemented)
- **Timezone:** `Asia/Kolkata`
