"""
Paper summarization - with optional AI enhancement.
"""
import re
from typing import Optional
from loguru import logger

from app.config import settings


class Summarizer:
    """Generate concise summaries of papers."""
    
    def __init__(self):
        self.openai_client = None
        
        if settings.openai_api_key:
            try:
                from openai import AsyncOpenAI
                self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
                logger.info("OpenAI client initialized for AI summaries")
            except ImportError:
                logger.warning("OpenAI package not installed, using basic summaries")
    
    async def summarize(self, paper: dict) -> str:
        """
        Generate a summary for a paper.
        Uses AI if available, otherwise extracts key sentences.
        """
        if self.openai_client:
            return await self._ai_summarize(paper)
        else:
            return self._basic_summarize(paper)
    
    async def _ai_summarize(self, paper: dict) -> str:
        """Use OpenAI to generate a concise summary."""
        try:
            prompt = f"""Summarize this scientific paper in 2-3 sentences for a synthetic biology researcher interested in metabolic engineering and protein production. Focus on the key findings and their practical implications.

Title: {paper['title']}

Abstract: {paper['abstract'][:2000]}

Respond with only the summary, no preamble."""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"AI summarization failed: {e}")
            return self._basic_summarize(paper)
    
    def _basic_summarize(self, paper: dict) -> str:
        """
        Extract key sentences from abstract as summary.
        Simple but effective fallback.
        """
        abstract = paper.get("abstract", "")
        
        if not abstract:
            return "No abstract available."
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', abstract)
        
        if len(sentences) <= 2:
            return abstract
        
        # Heuristics for important sentences:
        # - First sentence (background/intro)
        # - Sentences with "we show", "we demonstrate", "we found", "results"
        # - Last sentence (conclusion)
        
        important_patterns = [
            r"\bwe (show|demonstrate|found|developed|present|report)\b",
            r"\b(results?|findings?|demonstrate|significant|novel)\b",
            r"\b(conclude|conclusion|summary)\b",
        ]
        
        key_sentences = [sentences[0]]  # Always include first
        
        for sentence in sentences[1:-1]:
            for pattern in important_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    key_sentences.append(sentence)
                    break
            if len(key_sentences) >= 3:
                break
        
        # Add last sentence if not already included
        if sentences[-1] not in key_sentences and len(key_sentences) < 3:
            key_sentences.append(sentences[-1])
        
        summary = " ".join(key_sentences[:3])
        
        # Truncate if too long
        if len(summary) > 500:
            summary = summary[:497] + "..."
        
        return summary
    
    async def summarize_batch(self, papers: list[dict]) -> list[dict]:
        """Summarize multiple papers."""
        for paper in papers:
            paper["summary"] = await self.summarize(paper)
        
        logger.info(f"Summarized {len(papers)} papers")
        return papers
