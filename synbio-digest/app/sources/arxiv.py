"""
arXiv API client.

Documentation: https://info.arxiv.org/help/api/
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx
import feedparser
from loguru import logger

from app.config import settings


class ArXivClient:
    """Client for fetching papers from arXiv."""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    # Relevant arXiv categories
    CATEGORIES = [
        "q-bio.MN",  # Molecular Networks
        "q-bio.CB",  # Cell Behavior
        "q-bio.GN",  # Genomics
        "q-bio.BM",  # Biomolecules
        "cs.LG",     # Machine Learning (for ML in biology)
    ]
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def search(
        self,
        query: str,
        categories: list[str] = None,
        max_results: int = 50,
        days_back: int = 7
    ) -> list[dict]:
        """
        Search arXiv for papers.
        """
        if categories is None:
            categories = self.CATEGORIES
        
        # Build query with categories
        cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
        full_query = f"({query}) AND ({cat_query})"
        
        params = {
            "search_query": full_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        
        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            # Parse Atom feed
            feed = feedparser.parse(response.text)
            
            papers = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for entry in feed.entries:
                paper = self._parse_entry(entry)
                if paper and paper["published_date"] >= cutoff_date:
                    papers.append(paper)
            
            logger.info(f"arXiv search '{query}': found {len(papers)} recent papers")
            return papers
            
        except Exception as e:
            logger.error(f"arXiv search error: {e}")
            return []
    
    def _parse_entry(self, entry: dict) -> Optional[dict]:
        """Parse an arXiv entry into our format."""
        try:
            # Parse date
            published_str = entry.get("published", "")
            try:
                published = datetime.strptime(
                    published_str[:10], "%Y-%m-%d"
                )
            except:
                published = datetime.now()
            
            # Authors
            authors = [
                author.get("name", "")
                for author in entry.get("authors", [])
            ]
            
            # arXiv ID
            arxiv_id = entry.get("id", "").split("/abs/")[-1]
            
            # Categories
            categories = [
                tag.get("term", "")
                for tag in entry.get("tags", [])
            ]
            
            # DOI (if available)
            doi = None
            for link in entry.get("links", []):
                if link.get("title") == "doi":
                    doi = link.get("href", "").replace("http://dx.doi.org/", "")
            
            return {
                "id": f"arxiv:{arxiv_id}",
                "source": "arxiv",
                "title": entry.get("title", "").replace("\n", " "),
                "authors": authors,
                "abstract": entry.get("summary", "").replace("\n", " "),
                "published_date": published,
                "url": entry.get("link", ""),
                "doi": doi,
                "categories": categories,
            }
            
        except Exception as e:
            logger.error(f"Error parsing arXiv entry: {e}")
            return None
    
    async def fetch_recent_papers(self, queries: list[str]) -> list[dict]:
        """
        Fetch recent papers for multiple queries.
        Deduplicates by arXiv ID.
        """
        seen_ids = set()
        all_papers = []
        
        for query in queries:
            papers = await self.search(
                query,
                max_results=settings.max_papers_per_source,
                days_back=settings.lookback_days
            )
            
            for paper in papers:
                if paper["id"] not in seen_ids:
                    seen_ids.add(paper["id"])
                    all_papers.append(paper)
            
            await asyncio.sleep(3)  # arXiv rate limit: 1 request per 3 seconds
        
        logger.info(f"arXiv total: {len(all_papers)} unique papers")
        return all_papers
    
    async def close(self):
        await self.client.aclose()
