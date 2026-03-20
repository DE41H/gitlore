<div align="center">

# GITLORE

**AI-powered collaborative storytelling — with version control.**

*Fork a story. Commit a chapter. Star a universe.*

[![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-6.0-092E20?logo=django&logoColor=white)](https://djangoproject.com)
[![Claude API](https://img.shields.io/badge/Powered%20by-Claude%20AI-8A2BE2)](https://anthropic.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## What is GITLORE?

GITLORE is a collaborative writing platform that borrows the best ideas from software development — branching, forking, starring — and applies them to creative fiction.

You write a prompt. Claude writes the story. Someone else forks it into an alternate universe. A community stars the best ones. Repeat.

Every story is a tree. Every chapter is a commit. Every fork is a new branch of reality.

---

## How it Works

### Stories as Trees

Each **Series** is a story repository. Inside it, **Chapters** form a tree: every chapter can have a parent (the chapter it branches from) and any number of children (alternate continuations). One path through this tree is marked **canon** — the official storyline. The rest are alternate branches.

### Canon vs. Non-Canon

The canon lineage is enforced structurally:
- Only one root chapter per series can be canon
- A chapter can only be canon if its parent is also canon
- At most one canon child per parent

This makes the canonical story a single, clean path through the tree, while all the "what if?" chapters live alongside it.

### Spin-offs

A **spin-off** is a full copy of a series — world, characters, genres, and the entire canon lineage — attributed to a new author. The new author can then continue writing from any point in the copied lineage. The original series records the spin-off relationship.

### Semantic Search for Context

When Claude generates a new chapter, it doesn't read the entire story. Instead, chapter content, world descriptions, and character descriptions are embedded as 1536-dimensional vectors (stored in PostgreSQL with pgvector). The most semantically relevant passages are retrieved and passed as context — keeping API costs low and responses focused.

---

## Features

| Feature | Description |
|---|---|
| **AI Story Engine** | Claude generates story segments from your prompts, with relevant prior chapters retrieved via semantic (vector) search |
| **Canon Lineage** | One definitive path through each story tree; branches are preserved but clearly non-canon |
| **Spin-offs** | Fork any series at any chapter — world, characters, and canon lineage are all copied atomically |
| **Likes** | Atomic like/unlike with a denormalized counter; concurrency-safe via `select_for_update` |
| **GitHub-dark UI** | Markdown-rendered stories, branch visualization, GitHub-inspired aesthetic |
| **Credit System** | Free daily prompt token quota; paid tiers for unlimited access via Stripe |
| **Export** | Publish to Wattpad or Webtoon (Phase 4, planned) |

---

## Data Model

```
Series ──────────────── World (1:1)
  │                     └─ description, embedding
  ├── author (User FK)
  ├── spin_off (self-FK, nullable)
  ├── genres (M2M → Genre)
  ├── likes (M2M → User)
  └── characters ──────── Character
                          └─ name, description, embedding

Chapter (tree, self-FK via parent)
  ├── series (FK → Series)
  ├── parent (FK → self, nullable = root)
  ├── canon (bool)
  ├── prompt / content
  └── embedding
```

**Slugs** are auto-generated as `{slugified-name}-{uid_hex[:12]}` and are unique per parent scope (series or author).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Django 6 (Python 3.14), ORM, auth, admin |
| **AI** | Anthropic Claude API — story generation via Celery async tasks |
| **Database** | PostgreSQL + pgvector — story graph, semantic search (HNSW indexes) |
| **Task Queue** | Celery + Redis; 300s task time limit |
| **Infrastructure** | Docker + Nginx |
| **Frontend** | Django Templates (SSR) + HTMX + Tailwind CSS |
| **Payments** | Stripe — subscription tiers |

---

## Getting Started

### Prerequisites

- Python 3.14+
- PostgreSQL with pgvector extension
- Redis
- `uv` package manager

### Setup

```bash
# Clone the repo
git clone https://github.com/sreyash/gitlore.git
cd gitlore

# Install dependencies
uv sync

# Configure environment (copy and fill in values)
cp .env.example .env

# Apply migrations and run
uv run python manage.py migrate
uv run python manage.py runserver
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | Set to `"true"` for development |
| `DJANGO_ALLOWED_HOSTS` | Space-separated list of allowed hosts |
| `DATABASE_ENGINE` | e.g. `django.db.backends.postgresql` |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_HOST` | Database host |
| `POSTGRES_PORT` | Database port |
| `CELERY_BROKER_URL` | Redis URL for Celery |

### Running Tests

```bash
# All tests
uv run python manage.py test

# Specific test
uv run python manage.py test series.tests.ClassName.method
```

---

## Roadmap

```
Phase 1 — Foundation       Django · Docker · Claude API integration
Phase 2 — Core Logic       Fork/Spin-off mechanics · Canon lineage · Semantic search
Phase 3 — Interface        GitHub-inspired frontend · Trending · Markdown rendering
Phase 4 — Business         Stripe subscriptions · Wattpad/Webtoon export
Phase 5 — Launch           Production deployment · Community feedback loop
```

> Solo sprint · 9 weeks

---

## Why "version control for stories"?

- **Writer's block disappears** — you're a prompt architect, not a typist
- **Remixing is first-class** — "What if?" is a fork, not a copy-paste
- **Quality rises naturally** — the community surfaces creativity, not just volume
- **Nothing is lost** — every branch, every alternate ending is preserved in the tree

---

<div align="center">
  <sub>Built with Claude · Django · and a love for storytelling</sub>
</div>
