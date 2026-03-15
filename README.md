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

---

## Features

| Feature | Description |
|---|---|
| **AI Story Engine** | Claude generates high-fidelity story segments from your prompts, with full narrative continuity |
| **Fork & Branch** | Copy any story into your own "repository" and take it wherever you want |
| **Stars & Leaderboard** | A discovery engine that surfaces stories by quality (stars) and creative influence (forks) |
| **GitHub-dark UI** | Markdown-rendered stories, contribution heatmaps, branch visualization |
| **Credit System** | Free daily prompt tokens; paid tiers for unlimited access via Stripe |
| **Export** | Publish your branch directly to Wattpad or Webtoon |

---

## Tech Stack

- **Backend** — Django 6 (Python 3.14), REST API, auth, credit management
- **AI** — Anthropic Claude API with context-chained story nodes
- **Database** — PostgreSQL + pgvector (branching story graph, JSON metadata, and semantic search to minimize Claude API context)
- **Infrastructure** — Docker + Nginx
- **Frontend** — Django Templates (SSR) + HTMX for dynamic interactions, Tailwind CSS, GitHub-dark aesthetic with Markdown rendering

---

## Getting Started

```bash
# Clone the repo
git clone https://github.com/sreyash/gitlore.git
cd gitlore

# Install dependencies
uv sync

# Apply migrations and run
uv run python manage.py migrate
uv run python manage.py runserver
```

---

## Roadmap

```
Phase 1 — Foundation       Django · Docker · Claude API integration
Phase 2 — Core Logic       Fork/Commit mechanics · Story lineage tracking
Phase 3 — Interface        GitHub-inspired frontend · Trending · Markdown rendering
Phase 4 — Business         Stripe subscriptions · Wattpad/Webtoon export
Phase 5 — Launch           Production deployment · Community feedback loop
```

> Solo sprint · 9 weeks

---

## Why "version control for stories"?

- **Writer's block disappears** — you're a prompt architect, not a typist
- **Remixing is first-class** — "What if?" is a fork, not a copy-paste
- **Quality rises naturally** — the leaderboard rewards creativity, not just volume

---

<div align="center">
  <sub>Built with Claude · Django · and a love for storytelling</sub>
</div>
