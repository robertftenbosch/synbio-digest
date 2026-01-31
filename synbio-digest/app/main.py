"""
Main entry point for SynBio Weekly Digest.

Run with:
    python -m app.main          # Start server + scheduler
    python -m app.main --test   # Run digest now (test mode)
"""
import asyncio
import argparse
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from loguru import logger

from app.config import settings
from app.db.models import init_db, AsyncSessionLocal, Subscriber, Paper, DigestLog
from app.sources.pubmed import PubMedClient
from app.sources.biorxiv import BioRxivClient
from app.sources.arxiv import ArXivClient
from app.processing.filter import PaperFilter
from app.processing.summarize import Summarizer
from app.email.sender import EmailSender
from app.api.routes import router


# Scheduler instance
scheduler = AsyncIOScheduler()


async def save_papers_to_db(papers: list, included_ids: set):
    """Save all fetched papers to the database."""
    async with AsyncSessionLocal() as db:
        saved_count = 0
        for paper in papers:
            # Skip if already exists
            existing = await db.execute(
                select(Paper).where(Paper.id == paper["id"])
            )
            if existing.scalar_one_or_none():
                continue

            db_paper = Paper(
                id=paper["id"],
                source=paper["source"],
                title=paper["title"],
                authors=paper.get("authors"),
                abstract=paper.get("abstract"),
                published_date=paper.get("published_date"),
                url=paper.get("url"),
                doi=paper.get("doi"),
                summary=paper.get("summary"),
                relevance_score=paper.get("relevance_score"),
                categories=paper.get("categories"),
                included_in_digest=paper["id"] in included_ids,
                digest_date=datetime.utcnow() if paper["id"] in included_ids else None,
            )
            db.add(db_paper)
            saved_count += 1
        await db.commit()
        logger.info(f"Saved {saved_count} new papers to database")


async def run_digest_job():
    """
    Main job: fetch papers, filter, summarize, and send digest.
    """
    logger.info("=" * 60)
    logger.info("Starting weekly digest job")
    logger.info("=" * 60)
    
    try:
        # 1. Fetch papers from all sources
        logger.info("Fetching papers from sources...")
        
        pubmed = PubMedClient()
        biorxiv = BioRxivClient()
        arxiv = ArXivClient()
        
        pubmed_papers = await pubmed.fetch_recent_papers(settings.search_queries)
        biorxiv_papers = await biorxiv.search_relevant(settings.search_queries)
        arxiv_papers = await arxiv.fetch_recent_papers(settings.search_queries)
        
        await pubmed.close()
        await biorxiv.close()
        await arxiv.close()
        
        all_papers = pubmed_papers + biorxiv_papers + arxiv_papers
        logger.info(f"Total papers fetched: {len(all_papers)}")
        
        # 2. Score all papers and filter
        logger.info("Filtering and scoring papers...")
        paper_filter = PaperFilter()

        # Score and categorize all papers for storage
        for paper in all_papers:
            if "relevance_score" not in paper:
                paper["relevance_score"] = paper_filter.score_paper(paper)
                paper["categories"] = paper_filter.categorize_paper(paper)

        filtered_papers = paper_filter.filter_papers(
            all_papers,
            min_score=0.2,
            max_papers=30
        )

        # 2b. Save all papers to database
        included_ids = {p["id"] for p in filtered_papers}
        await save_papers_to_db(all_papers, included_ids)

        if not filtered_papers:
            logger.warning("No relevant papers found this week")
            return
        
        # 3. Generate summaries
        logger.info("Generating summaries...")
        summarizer = Summarizer()
        papers_with_summaries = await summarizer.summarize_batch(filtered_papers)
        
        # 4. Get subscribers
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Subscriber).where(Subscriber.confirmed == True)
            )
            subscribers = result.scalars().all()
            
            if not subscribers:
                logger.warning("No subscribers to send to")
                # For testing, print papers anyway
                for p in papers_with_summaries[:5]:
                    logger.info(f"- {p['title'][:80]}... (score: {p['relevance_score']:.2f})")
                return
            
            subscriber_list = [
                {
                    "email": s.email,
                    "name": s.name,
                    "unsubscribe_token": s.unsubscribe_token,
                }
                for s in subscribers
            ]
        
        # 5. Send emails
        logger.info(f"Sending digest to {len(subscriber_list)} subscribers...")
        sender = EmailSender()
        stats = await sender.send_to_all_subscribers(
            papers=papers_with_summaries,
            subscribers=subscriber_list,
        )
        
        # 6. Log results
        async with AsyncSessionLocal() as db:
            log = DigestLog(
                paper_count=len(papers_with_summaries),
                subscriber_count=len(subscriber_list),
                paper_ids=[p["id"] for p in papers_with_summaries],
                success=stats["failed"] == 0,
            )
            db.add(log)
            await db.commit()
        
        logger.info("=" * 60)
        logger.info(f"Digest complete! Sent {stats['success']}/{stats['total']} emails")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Digest job failed: {e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Initializing database...")
    await init_db()
    
    # Schedule weekly digest
    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    day_of_week = day_map.get(settings.digest_day.lower(), 0)
    
    scheduler.add_job(
        run_digest_job,
        trigger=CronTrigger(
            day_of_week=day_of_week,
            hour=settings.digest_hour,
            minute=settings.digest_minute,
        ),
        id="weekly_digest",
        name="Weekly Digest",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Scheduled digest for {settings.digest_day} at "
        f"{settings.digest_hour:02d}:{settings.digest_minute:02d}"
    )
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    logger.info("Scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="SynBio Weekly Digest",
    description="Weekly digest of synthetic biology and metabolic engineering papers",
    lifespan=lifespan,
)

# Include routes
app.include_router(router)


# Health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "scheduler_running": scheduler.running,
        "next_digest": str(scheduler.get_job("weekly_digest").next_run_time)
        if scheduler.get_job("weekly_digest")
        else None,
    }


# Search page HTML
SEARCH_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Search - SynBio Weekly Digest</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        h1 {
            color: #0d9488;
            margin-top: 0;
        }
        .search-form {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        .search-form input[type="text"] {
            flex: 1;
            min-width: 200px;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 16px;
        }
        .search-form select {
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 16px;
            background: white;
        }
        .search-form input:focus, .search-form select:focus {
            outline: none;
            border-color: #0d9488;
        }
        .search-form button {
            padding: 12px 24px;
            background: #0d9488;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }
        .search-form button:hover { background: #0f766e; }
        .results-info {
            color: #6b7280;
            margin-bottom: 16px;
        }
        .paper {
            border-bottom: 1px solid #e5e7eb;
            padding: 16px 0;
        }
        .paper:last-child { border-bottom: none; }
        .paper-title {
            font-size: 18px;
            font-weight: 600;
            color: #111827;
            margin-bottom: 4px;
        }
        .paper-title a {
            color: #0d9488;
            text-decoration: none;
        }
        .paper-title a:hover { text-decoration: underline; }
        .paper-meta {
            font-size: 14px;
            color: #6b7280;
            margin-bottom: 8px;
        }
        .paper-meta span { margin-right: 16px; }
        .paper-abstract {
            color: #4b5563;
            font-size: 14px;
        }
        .category-tag {
            display: inline-block;
            background: #e0f2f1;
            color: #0d9488;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 4px;
        }
        .pagination {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 20px;
        }
        .pagination button {
            padding: 8px 16px;
            background: #e5e7eb;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        .pagination button:hover { background: #d1d5db; }
        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .loading { color: #6b7280; text-align: center; padding: 40px; }
        .nav-link {
            color: #0d9488;
            text-decoration: none;
            margin-right: 16px;
        }
        .nav-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="card">
        <div style="margin-bottom: 16px;">
            <a href="/" class="nav-link">Home</a>
        </div>
        <h1>Paper Search</h1>
        <form class="search-form" id="search-form">
            <input type="text" name="q" placeholder="Search keywords..." id="search-input">
            <select name="category" id="category-select">
                <option value="">All categories</option>
                <option value="metabolic_engineering">Metabolic Engineering</option>
                <option value="protein_expression">Protein Expression</option>
                <option value="synthetic_biology">Synthetic Biology</option>
                <option value="codon_optimization">Codon Optimization</option>
                <option value="fermentation">Fermentation</option>
                <option value="strain_engineering">Strain Engineering</option>
                <option value="plasma_proteins">Plasma Proteins</option>
                <option value="computational_tools">Computational Tools</option>
            </select>
            <select name="source" id="source-select">
                <option value="">All sources</option>
                <option value="pubmed">PubMed</option>
                <option value="biorxiv">bioRxiv</option>
                <option value="arxiv">arXiv</option>
            </select>
            <button type="submit">Search</button>
        </form>
    </div>

    <div class="card">
        <div id="results-info" class="results-info"></div>
        <div id="results"></div>
        <div class="pagination" id="pagination" style="display: none;">
            <button id="prev-btn" onclick="changePage(-1)">Previous</button>
            <span id="page-info"></span>
            <button id="next-btn" onclick="changePage(1)">Next</button>
        </div>
    </div>

    <script>
        let currentOffset = 0;
        const limit = 20;
        let total = 0;

        document.getElementById('search-form').addEventListener('submit', (e) => {
            e.preventDefault();
            currentOffset = 0;
            search();
        });

        async function search() {
            const q = document.getElementById('search-input').value;
            const category = document.getElementById('category-select').value;
            const source = document.getElementById('source-select').value;

            const params = new URLSearchParams();
            if (q) params.set('q', q);
            if (category) params.set('category', category);
            if (source) params.set('source', source);
            params.set('limit', limit);
            params.set('offset', currentOffset);

            document.getElementById('results').innerHTML = '<div class="loading">Loading...</div>';

            const response = await fetch('/api/papers/search?' + params);
            const data = await response.json();

            total = data.total;
            displayResults(data);
        }

        function displayResults(data) {
            const resultsDiv = document.getElementById('results');
            const infoDiv = document.getElementById('results-info');
            const pagination = document.getElementById('pagination');

            if (data.papers.length === 0) {
                infoDiv.textContent = 'No papers found.';
                resultsDiv.innerHTML = '';
                pagination.style.display = 'none';
                return;
            }

            const start = data.offset + 1;
            const end = Math.min(data.offset + data.papers.length, data.total);
            infoDiv.textContent = `Showing ${start}-${end} of ${data.total} papers`;

            resultsDiv.innerHTML = data.papers.map(paper => `
                <div class="paper">
                    <div class="paper-title">
                        <a href="${paper.url || '#'}" target="_blank">${escapeHtml(paper.title)}</a>
                    </div>
                    <div class="paper-meta">
                        <span><strong>Source:</strong> ${paper.source}</span>
                        <span><strong>Date:</strong> ${paper.published_date ? paper.published_date.split('T')[0] : 'N/A'}</span>
                        ${paper.relevance_score ? `<span><strong>Score:</strong> ${paper.relevance_score.toFixed(2)}</span>` : ''}
                    </div>
                    ${paper.categories && paper.categories.length > 0 ?
                        `<div style="margin-bottom: 8px;">
                            ${paper.categories.map(c => `<span class="category-tag">${c.replace('_', ' ')}</span>`).join('')}
                        </div>` : ''}
                    <div class="paper-abstract">${escapeHtml(paper.abstract || 'No abstract available.')}</div>
                </div>
            `).join('');

            // Update pagination
            pagination.style.display = data.total > limit ? 'flex' : 'none';
            document.getElementById('prev-btn').disabled = currentOffset === 0;
            document.getElementById('next-btn').disabled = currentOffset + limit >= data.total;
            document.getElementById('page-info').textContent =
                `Page ${Math.floor(currentOffset / limit) + 1} of ${Math.ceil(data.total / limit)}`;
        }

        function changePage(direction) {
            currentOffset += direction * limit;
            search();
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Initial load - show all papers
        search();
    </script>
</body>
</html>
"""


@app.get("/search", include_in_schema=False)
async def search_page():
    """Serve the search page."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=SEARCH_PAGE_HTML)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SynBio Weekly Digest")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run digest immediately (test mode)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on",
    )
    args = parser.parse_args()
    
    if args.test:
        # Run digest immediately
        logger.info("Running test digest...")
        asyncio.run(init_db())
        asyncio.run(run_digest_job())
    else:
        # Start server
        import uvicorn
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=args.port,
            reload=True,
        )


if __name__ == "__main__":
    main()
