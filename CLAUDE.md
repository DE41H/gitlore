# CLAUDE.md

GITLORE — AI-powered collaborative storytelling with version control semantics (fork, spin-off, like). Users write prompts, Gemini generates chapters, others branch from any point in the tree.

**Stack:** Python 3.14.3 · Django 6.0.3 · PostgreSQL + pgvector · Gemini API · Celery + Redis · Docker + Nginx · Stripe
**Frontend:** Django Templates (SSR) · HTMX · Tailwind CSS · `uv`

---

## Layout

```
config/          # Django project root — settings, urls, wsgi, asgi, celery
series/          # The only registered Django app
  models/        # One file per model group
  services/      # All business logic — views must call these, never write logic in views
  ai/            # Gemini client, embedding, RAG-based generation
  tasks.py       # Celery tasks (wrap ai/ functions)
  signals.py     # post_save → on_commit → .delay() for embeddings + generation
  views.py       # Thin — delegates everything to services/
  admin.py / tests.py
templates/       # SSR Django templates
```

`config/` is the project root, not an app. DB table prefix: `series_`. In raw SQL always use `Model._meta.db_table` — never hardcode.

---

## Commands

```bash
uv sync
uv run python manage.py runserver
uv run python manage.py test
uv run python manage.py test series.tests.ClassName.method
uv run python manage.py makemigrations && uv run python manage.py migrate
```

---

## Data Model

### Core models (`series/models/`)

| Model | Notable fields | Notes |
|-------|---------------|-------|
| `Series` | `name`, `synopsis`, `author` (FK→User), `visibility`, `world` (OneToOne→World), `genres` (M2M→Genre), `likes` (M2M→User), `like_count`, `view_count`, `spin_off` (self-FK), `spin_off_chapter` (FK→Chapter) | slug = `{slugified-name}-{uid.hex[:12]}`, unique per author |
| `Chapter` | `name`, `prompt` (max 10000), `content` (nullable), `status`, `canon`, `series` (FK), `parent` (self-FK, nullable) | Tree node; `parent=NULL` = root; `PROTECT` on parent delete (children are re-parented first in `delete()`); slug unique per series |
| `World` | `description` (max 5000) | Exactly one per Series via `Series.world` (reverse: `world.series`) |
| `Character` | `name`, `description` (max 2000), `series` (FK) | Unique name per series |
| `Genre` | `name` (unique), `slug`, `uid` | Shared across series via M2M |

`ChapterStatus`: `pending` → `generating` → `done` / `failed`

### Chunk models (embeddings stored separately)

| Model | Fields | Related name |
|-------|--------|-------------|
| `WorldChunk` | `chunk` (TextField), `embedding` (VectorField 1536d), `world` (FK) | `world.chunks` |
| `CharacterChunk` | `chunk` (TextField), `embedding` (VectorField 1536d), `character` (FK) | `character.chunks` |
| `ChapterChunk` | `chunk` (TextField), `embedding` (VectorField 1536d), `chapter` (FK) | `chapter.chunks` |

`EMBEDDING_DIMENSIONS = 1536` — defined in `series/ai/embedding.py`.
All chunk models: HNSW index (`vector_cosine_ops`, m=16, ef_construction=64).

### DB constraints (Chapter)

| Constraint | Type | Rule |
|-----------|------|------|
| `unique_canon_root_per_series` | UniqueConstraint | `canon=True, parent=NULL` unique per series |
| `unique_canon_child_per_parent` | UniqueConstraint | `canon=True` unique per `(parent, series)` |
| `canon_chapter_must_be_done` | CheckConstraint | `canon=True` requires `status=done` |
| `unique_chapter_slug_per_series` | UniqueConstraint | slug unique per series |

---

## Services (`series/services/`)

**Rule:** views call services. No ORM queries in views.

### `canon.py`

```python
toggle_canon(chapter_id: int) -> None
```
Atomic. `select_for_update()` + `select_related("parent")` + `prefetch_related("children")`. **Unset:** raises `ValueError` if chapter has canon children. **Set:** raises `ValueError` if status≠DONE, parent non-canon, duplicate canon root, or duplicate canon sibling.

### `social.py`

```python
toggle_like(series_id: int, user_id: int) -> None
add_view(series_id: int) -> None
```
`toggle_like`: `select_for_update()` + `prefetch_related("likes")` → checks `any(u.pk == user_id for u in series.likes.all())` (uses cache, no extra query) → `F()` increment/decrement.
`add_view`: single `UPDATE` with `F()`.

### `authoring.py`

```python
replicate(series_id: int, author_id: int, spin_off_chapter_id: int | None = None) -> int
start_spin_off(chapter_id: int, author_id: int) -> int
```
`replicate`: atomic copy of Series + World + WorldChunks (with `chunk` text) + Characters + CharacterChunks (with `chunk` text) + Genres. Returns new `series.pk`.
`start_spin_off`: validates chapter + full lineage are `DONE`, saves `original_lineage_ids` before mutation, calls `replicate`, bulk-creates lineage chapters root-first, re-links parents, copies ChapterChunks by original ID using `defaultdict`. Returns new `series_id`.

### `tree.py`

```python
get_lineage(chapter_id: int, fields: list[str] | None = None) -> list[Chapter]   # self → root
get_descendants(chapter_id: int, fields: list[str] | None = None) -> list[Chapter]  # BFS
change_parent(chapter_id: int, new_parent_id: int) -> None
```
Both CTE functions accept optional `fields` to limit SELECT columns (always includes `id`, `parent_id`).
`change_parent`: `select_for_update()` on both chapters; checks same series, non-canon, parent unchanged, and `new_parent_id not in {c.pk for c in get_descendants(chapter_id)}` for cycle detection.

### `text.py`

```python
split_text(text: str) -> list[str]
```
LangChain `RecursiveCharacterTextSplitter` (tiktoken/gpt2), chunk_size=1000, overlap=200. Module-level singleton splitter.

### Planned view helpers (not yet implemented)

Add to services as views are built:

- **`authoring.py`**: `create_series(author_id, name, synopsis, visibility, world_description, genre_ids) -> int` · `update_series(series_id, **fields)` · `add_character(series_id, name, description) -> int` · `update_character(character_id, **fields)` · `update_world(world_id, description)` · `delete_character(character_id)`
- **`chapter.py` (new)**: `create_chapter(series_id, parent_id, name, prompt) -> int` · `get_series_tree(series_id) -> list[Chapter]` · `get_chapter_detail(chapter_id) -> Chapter` · `delete_chapter(chapter_id, user_id)`
- **`social.py`**: `get_like_status(series_id, user_id) -> bool`
- **`series.py` (new)**: `get_series_detail(series_id) -> Series` · `get_public_series(author_id=None) -> QuerySet` · `get_user_series(user_id) -> QuerySet`

---

## AI Layer (`series/ai/`)

### `gemini.py`
Singleton client. `generation_model = "gemini-2.5-flash"`, `embedding_model = "text-embedding-004"`.

### `embedding.py`

```python
EMBEDDING_DIMENSIONS = 1536
EMBED_BATCH_SIZE = 100

get_embeddings(text_list: list[str], task_type: str = "retrieval_document") -> list
embed_world(world_id: int) -> None
embed_character(character_id: int) -> None
embed_series(series_id: int) -> None
```
`get_embeddings`: batches at 100; raises `ValueError` if any batch returns empty.
`embed_character`: prepends `"{name}: "` to each chunk before embedding.
`embed_series`: single batched API call for world + all characters (world first, then characters in dict order); slices `all_embeddings` by offset to assign per-character.

### `generation.py`

```python
TEMPERATURE = 0.7

generate_content(chapter_id: int) -> None
get_context(chapter_id: int, series_id: int, embedding: list[float]) -> str
```
`generate_content`: `select_related("series")`; raises `ValueError` if chapter already has content; embeds prompt with `task_type="retrieval_query"`; calls `get_context`; sets `generating` → saves; calls Gemini; sets `done`/`failed`; bare `raise` on exception (preserves type for Celery retry).
`get_context`: 4 vector-similarity queries (world chunks ×5, character chunks ×10, chapter chunks ×10, lineage `[:-1][-3:]`); assembles sections with per-section char caps (world 2000, characters 3000, story-so-far 4000, related 2000) → ~3000 token ceiling.

---

## Celery Tasks (`series/tasks.py`)

All: `bind=True, max_retries=3, retry_backoff=True, autoretry_for=(APIError, ConnectionError, TimeoutError)`.

| Task | Wraps |
|------|-------|
| `create_series_embeddings(series_id)` | `embed_series` |
| `create_world_embeddings(world_id)` | `embed_world` |
| `create_character_embeddings(character_id)` | `embed_character` |
| `generate_chapter_content(chapter_id)` | `generate_content` |

---

## Signals (`series/signals.py`)

All fire via `on_commit(lambda: task.delay(...))` — never dispatches inside a rolled-back transaction.

| Signal | Condition | Task |
|--------|-----------|------|
| `Character` post_save | `created` OR `update_fields is None` OR `{name, description} ∩ update_fields` | `create_character_embeddings` |
| `World` post_save | `created` OR `update_fields is None` OR `{description} ∩ update_fields` | `create_world_embeddings` |
| `Series` post_save | `created` | `create_series_embeddings` |
| `Chapter` post_save | `created` | `generate_chapter_content` |

`update_fields=None` (full `.save()`) always triggers re-embedding.

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `"true"` enables debug |
| `DJANGO_ALLOWED_HOSTS` | Space-separated |
| `DATABASE_ENGINE` | `django.db.backends.postgresql` |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | DB connection |
| `CELERY_BROKER_URL` | Redis URL (also cache backend) |
| `GOOGLE_API_KEY` | Gemini API key |

---

## Architecture Notes

- `like_count` / `view_count` are denormalized; drift if M2M modified outside `social.py`.
- `start_spin_off` mutates lineage objects in-place (`pk=None`) before `bulk_create`; original PKs saved to `original_lineage_ids` for chunk copy.
- Celery task time limit: 300s. Generation is async; poll status via HTMX.
- Credit system: per-user prompt token quota; Stripe paid tiers bypass limits.
- Timezone: `Asia/Kolkata`.
