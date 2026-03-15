# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GITLORE is a GitHub-inspired collaborative AI storytelling platform. Users write prompts, Claude generates story segments, and others can fork/star them — applying version control concepts (branches, commits, forks, stars) to creative fiction.

**Stack:** Python 3.14.3 · Django 6.0.3 · PostgreSQL + pgvector · Anthropic Claude API · Docker + Nginx · Stripe
**Frontend:** Django Templates (SSR) · HTMX · Tailwind CSS
**Package manager:** `uv`

## Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run python manage.py runserver

# Run all tests
uv run python manage.py test

# Run a single test
uv run python manage.py test config.tests.TestClassName.test_method

# Database migrations
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## Architecture

- Single Django app: `config/` — models, views, admin, and tests all live here for now
- No `manage.py` yet; it will be added at the project root when the Django project scaffold is completed
- **Story graph model:** Stories are nodes in a parent/child tree — each fork creates a child node linked to its parent, enabling lineage tracking
- **Claude integration:** Story generation uses pgvector semantic search to retrieve only the top-K most relevant story nodes as context, rather than passing all previous nodes — keeps token usage minimal as stories grow
- **Credit system:** Per-user prompt token quota enforced in Django; paid tiers via Stripe bypass limits
- **Export targets:** Wattpad and Webtoon (Phase 4)
- **Frontend:** Server-side rendered Django templates with HTMX for dynamic interactions (story generation streaming, fork/star without page reloads) and Tailwind CSS for styling
