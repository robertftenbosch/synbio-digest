# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SynBio Weekly Digest is an automated scientific paper aggregation and email delivery system. It monitors PubMed, bioRxiv/medRxiv, and arXiv for new publications in synthetic biology and metabolic engineering, scores them for relevance, generates summaries, and sends weekly digest emails to subscribers.

## Commands

**Run the application:**
```bash
cd synbio-digest
python -m app.main              # Start server + scheduler
python -m app.main --test       # Send a test digest immediately
python -m app.main --port 8080  # Custom port
```

**Development with hot reload:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Setup:**
```bash
cd synbio-digest
pip install -r requirements.txt
cp .env.example .env  # Then edit with your credentials
```

## Architecture

The application uses FastAPI with async/await throughout. APScheduler runs the weekly digest job.

**Key modules:**
- `app/main.py` - Entry point, FastAPI app, scheduler setup, `run_digest_job()` function
- `app/config.py` - Pydantic settings loaded from environment variables
- `app/sources/` - Paper fetchers (pubmed.py, biorxiv.py, arxiv.py) - each has `fetch_recent_papers()`
- `app/processing/filter.py` - Relevance scoring with weighted keywords, `score_paper()` and `filter_papers()`
- `app/processing/summarize.py` - AI summaries (OpenAI) with heuristic fallback
- `app/email/sender.py` - Multi-provider email (Resend primary, SMTP backup, console for testing)
- `app/db/models.py` - SQLAlchemy models: Paper, Subscriber, DigestLog
- `app/api/routes.py` - REST endpoints for subscription management

**Digest job workflow:** Fetch papers from all sources (async concurrent) → Score and filter (top 30, min score 0.2) → Categorize → Generate summaries → Send emails → Log results

## Configuration

All settings are in `.env` (see `.env.example`). Key variables:
- `EMAIL_PROVIDER` - resend, smtp, or console
- `RESEND_API_KEY` / SMTP credentials
- `OPENAI_API_KEY` - Optional, enables AI summaries
- `DIGEST_DAY`, `DIGEST_HOUR` - Schedule (default: Monday 07:00)
- `DATABASE_URL` - SQLite by default

## API Endpoints

- `GET /health` - Scheduler status
- `POST /api/subscribe` - `{email, name?, interests?}`
- `GET /api/unsubscribe?token={token}`
- `GET /api/subscribers/count`
- `GET /` - Landing page with subscription form

## Rate Limiting

Paper source APIs have built-in delays: PubMed/bioRxiv 0.3-0.5s, arXiv 3s per request.
