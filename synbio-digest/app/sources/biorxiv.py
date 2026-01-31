"""
bioRxiv/medRxiv API client.

Documentation: https://api.biorxiv.org/
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx
from loguru import logger

from app.config import settings


class BioRxivClient:
    """Client for fetching preprints from bioRxiv and medRxiv."""
    
    BASE_URL = "https://api.biorxiv.org"
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def fetch_recent(
        self,
        server: str = "biorxiv",  # biorxiv or medrxiv
        days_back: int = 7,
        max_results: int = 100
    ) -> list[dict]:
        """
        Fetch recent preprints.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        url = f"{self.BASE_URL}/details/{server}/{start_date:%Y-%m-%d}/{end_date:%Y-%m-%d}"
        
        all_papers = []
        cursor = 0
        
        while len(all_papers) < max_results:
            try:
                response = await self.client.get(
                    url,
                    params={"cursor": cursor}
                )
                response.raise_for_status()
                data = response.json()
                
                collection = data.get("collection", [])
                if not collection:
                    break
                
                for item in collection:
                    paper = self._parse_preprint(item, server)
                    if paper:
                        all_papers.append(paper)
                
                # Check if more results
                messages = data.get("messages", [])
                if messages and messages[0].get("status") == "no posts found":
                    break
                
                cursor += len(collection)
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"bioRxiv fetch error: {e}")
                break
        
        logger.info(f"{server}: fetched {len(all_papers)} preprints")
        return all_papers[:max_results]
    
    def _parse_preprint(self, item: dict, server: str) -> Optional[dict]:
        """Parse a bioRxiv/medRxiv item into our format."""
        try:
            # Parse date
            date_str = item.get("date", "")
            try:
                published = datetime.strptime(date_str, "%Y-%m-%d")
            except:
                published = datetime.now()
            
            # Authors
            authors_str = item.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()]
            
            doi = item.get("doi", "")
            
            return {
                "id": f"{server}:{doi}",
                "source": server,
                "title": item.get("title", ""),
                "authors": authors,
                "abstract": item.get("abstract", ""),
                "published_date": published,
                "url": f"https://www.{server}.org/content/{doi}",
                "doi": doi,
                "category": item.get("category", ""),
            }
            
        except Exception as e:
            logger.error(f"Error parsing {server} preprint: {e}")
            return None
    
    async def search_relevant(self, queries: list[str]) -> list[dict]:
        """
        Fetch recent preprints and filter for relevance.
        bioRxiv API doesn't support search, so we fetch all and filter.
        """
        # Fetch from both servers
        biorxiv_papers = await self.fetch_recent(
            "biorxiv",
            days_back=settings.lookback_days,
            max_results=500  # Fetch more, filter later
        )
        
        medrxiv_papers = await self.fetch_recent(
            "medrxiv",
            days_back=settings.lookback_days,
            max_results=200
        )
        
        all_papers = biorxiv_papers + medrxiv_papers
        
        # Filter by category and keywords
        relevant_categories = {
            "synthetic biology",
            "systems biology",
            "bioengineering",
            "molecular biology",
            "microbiology",
            "biochemistry",
            "genomics",
            "genetics",
        }
        
        # Build keyword set from queries
        keywords = set()
        for query in queries:
            keywords.update(query.lower().split())
        
        filtered = []
        for paper in all_papers:
            # Check category
            category = paper.get("category", "").lower()
            if any(cat in category for cat in relevant_categories):
                filtered.append(paper)
                continue
            
            # Check title/abstract for keywords
            text = f"{paper['title']} {paper['abstract']}".lower()
            if any(kw in text for kw in keywords):
                filtered.append(paper)
        
        logger.info(f"bioRxiv/medRxiv: {len(filtered)} relevant papers from {len(all_papers)} total")
        return filtered
    
    async def close(self):
        await self.client.aclose()
