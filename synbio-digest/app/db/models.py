"""
Database models for papers and subscribers.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Boolean, Text, Float, Integer, JSON, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

Base = declarative_base()


class Paper(Base):
    """Cached paper from any source."""
    __tablename__ = "papers"
    
    id = Column(String, primary_key=True)  # DOI or source-specific ID
    source = Column(String, nullable=False)  # pubmed, biorxiv, arxiv
    
    title = Column(String, nullable=False)
    authors = Column(JSON)  # List of author names
    abstract = Column(Text)
    
    published_date = Column(DateTime)
    url = Column(String)
    doi = Column(String)
    
    # Our additions
    summary = Column(Text)  # AI-generated summary
    relevance_score = Column(Float)  # 0-1
    categories = Column(JSON)  # ["metabolic_engineering", "codon_optimization", ...]
    
    # Tracking
    fetched_at = Column(DateTime, default=datetime.utcnow)
    included_in_digest = Column(Boolean, default=False)
    digest_date = Column(DateTime)

    __table_args__ = (
        Index("ix_papers_source", "source"),
        Index("ix_papers_published_date", "published_date"),
    )


class Subscriber(Base):
    """Email subscriber."""
    __tablename__ = "subscribers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    
    # Preferences
    interests = Column(JSON)  # ["metabolic_engineering", "protein_expression", ...]
    frequency = Column(String, default="weekly")  # weekly, daily
    
    # Status
    confirmed = Column(Boolean, default=False)
    confirmation_token = Column(String)
    unsubscribe_token = Column(String)
    
    # Tracking
    subscribed_at = Column(DateTime, default=datetime.utcnow)
    last_email_sent = Column(DateTime)
    emails_received = Column(Integer, default=0)


class DigestLog(Base):
    """Log of sent digests."""
    __tablename__ = "digest_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    paper_count = Column(Integer)
    subscriber_count = Column(Integer)
    paper_ids = Column(JSON)  # List of paper IDs included
    
    # Status
    success = Column(Boolean)
    error_message = Column(Text)


# Database setup
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
