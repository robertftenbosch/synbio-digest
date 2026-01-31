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
        
        # 2. Filter and score
        logger.info("Filtering and scoring papers...")
        paper_filter = PaperFilter()
        filtered_papers = paper_filter.filter_papers(
            all_papers,
            min_score=0.2,
            max_papers=30
        )
        
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
