"""
PubMed E-utilities API client.

Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx
import xmltodict
from loguru import logger

from app.config import settings


class PubMedClient:
    """Client for fetching papers from PubMed."""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def search(
        self, 
        query: str, 
        max_results: int = 50,
        days_back: int = 7
    ) -> list[str]:
        """
        Search PubMed and return list of PMIDs.
        """
        # Date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        date_filter = f"{start_date:%Y/%m/%d}:{end_date:%Y/%m/%d}[PDAT]"
        full_query = f"({query}) AND {date_filter}"
        
        params = {
            "db": "pubmed",
            "term": full_query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "date",
        }
        
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/esearch.fcgi",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            pmids = data.get("esearchresult", {}).get("idlist", [])
            logger.info(f"PubMed search '{query}': found {len(pmids)} papers")
            return pmids
            
        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            return []
    
    async def fetch_details(self, pmids: list[str]) -> list[dict]:
        """
        Fetch paper details for a list of PMIDs.
        """
        if not pmids:
            return []
        
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params=params
            )
            response.raise_for_status()
            
            data = xmltodict.parse(response.text)
            articles = data.get("PubmedArticleSet", {}).get("PubmedArticle", [])
            
            # Ensure it's a list
            if isinstance(articles, dict):
                articles = [articles]
            
            papers = []
            for article in articles:
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)
            
            return papers
            
        except Exception as e:
            logger.error(f"PubMed fetch error: {e}")
            return []
    
    def _parse_article(self, article: dict) -> Optional[dict]:
        """Parse a PubMed article into our format."""
        try:
            medline = article.get("MedlineCitation", {})
            article_data = medline.get("Article", {})
            
            # PMID
            pmid = medline.get("PMID", {})
            if isinstance(pmid, dict):
                pmid = pmid.get("#text", "")
            
            # Title
            title = article_data.get("ArticleTitle", "")
            if isinstance(title, dict):
                title = title.get("#text", "")
            
            # Abstract
            abstract_data = article_data.get("Abstract", {}).get("AbstractText", "")
            if isinstance(abstract_data, list):
                abstract = " ".join(
                    item.get("#text", item) if isinstance(item, dict) else str(item)
                    for item in abstract_data
                )
            elif isinstance(abstract_data, dict):
                abstract = abstract_data.get("#text", "")
            else:
                abstract = str(abstract_data) if abstract_data else ""
            
            # Authors
            author_list = article_data.get("AuthorList", {}).get("Author", [])
            if isinstance(author_list, dict):
                author_list = [author_list]
            
            authors = []
            for author in author_list:
                if isinstance(author, dict):
                    last = author.get("LastName", "")
                    first = author.get("ForeName", "")
                    if last:
                        authors.append(f"{first} {last}".strip())
            
            # Date
            pub_date = article_data.get("ArticleDate", [])
            if isinstance(pub_date, list) and pub_date:
                pub_date = pub_date[0]
            if isinstance(pub_date, dict):
                year = pub_date.get("Year", "")
                month = pub_date.get("Month", "01")
                day = pub_date.get("Day", "01")
                try:
                    published = datetime(int(year), int(month), int(day))
                except:
                    published = datetime.now()
            else:
                published = datetime.now()
            
            # DOI
            doi = None
            id_list = article_data.get("ELocationID", [])
            if isinstance(id_list, dict):
                id_list = [id_list]
            for eid in id_list:
                if isinstance(eid, dict) and eid.get("@EIdType") == "doi":
                    doi = eid.get("#text", "")
                    break
            
            return {
                "id": f"pubmed:{pmid}",
                "source": "pubmed",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published_date": published,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi": doi,
            }
            
        except Exception as e:
            logger.error(f"Error parsing PubMed article: {e}")
            return None
    
    async def fetch_recent_papers(self, queries: list[str]) -> list[dict]:
        """
        Fetch recent papers for multiple queries.
        Deduplicates by PMID.
        """
        all_pmids = set()
        
        for query in queries:
            pmids = await self.search(
                query,
                max_results=settings.max_papers_per_source,
                days_back=settings.lookback_days
            )
            all_pmids.update(pmids)
            await asyncio.sleep(0.5)  # Rate limiting
        
        logger.info(f"Total unique PMIDs: {len(all_pmids)}")
        
        # Fetch in batches of 100
        all_papers = []
        pmid_list = list(all_pmids)
        
        for i in range(0, len(pmid_list), 100):
            batch = pmid_list[i:i+100]
            papers = await self.fetch_details(batch)
            all_papers.extend(papers)
            await asyncio.sleep(0.5)
        
        return all_papers
    
    async def close(self):
        await self.client.aclose()
