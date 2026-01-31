"""
Paper filtering and relevance scoring.
"""
import re
from typing import Optional
from loguru import logger


# Keywords for relevance scoring
KEYWORDS = {
    # High relevance (core topics)
    "high": [
        "metabolic engineering",
        "metabolic pathway",
        "synthetic biology",
        "pathway design",
        "flux balance",
        "recombinant protein",
        "heterologous expression",
        "codon optimization",
        "cell factory",
        "bioproduction",
        "protein expression",
        "E. coli expression",
        "yeast expression",
        "Pichia pastoris",
        "CHO cells",
        "fermentation optimization",
        "metabolic flux",
        "gene circuit",
        "genetic circuit",
        "CRISPR metabolic",
        "pathway engineering",
        "biosynthesis",
        "biomanufacturing",
    ],
    
    # Medium relevance
    "medium": [
        "expression system",
        "plasmid",
        "promoter strength",
        "ribosome binding",
        "protein folding",
        "secretion pathway",
        "genome engineering",
        "strain engineering",
        "bioprocess",
        "fed-batch",
        "continuous culture",
        "enzyme engineering",
        "directed evolution",
        "high-throughput screening",
    ],
    
    # Low relevance but still interesting
    "low": [
        "biotechnology",
        "microbial",
        "bacterial",
        "cultivation",
        "bioreactor",
        "downstream processing",
        "protein purification",
    ],
}

# Keywords that indicate low relevance for our use case
NEGATIVE_KEYWORDS = [
    "clinical trial",
    "patient",
    "diagnosis",
    "disease progression",
    "epidemiology",
    "cancer treatment",
    "drug delivery",
    "nanoparticle",
    "imaging",
    "phylogenetic",
    "ecology",
    "environmental sample",
]

# Specific proteins we care about (for plasma project)
PLASMA_PROTEINS = [
    "albumin",
    "serum albumin",
    "immunoglobulin",
    "clotting factor",
    "coagulation factor",
    "fibrinogen",
    "factor VIII",
    "factor IX",
    "von Willebrand",
    "antithrombin",
    "transferrin",
    "hemoglobin",
]


class PaperFilter:
    """Filter and score papers for relevance."""
    
    def __init__(self):
        # Compile regex patterns for efficiency
        self.high_patterns = [
            re.compile(rf"\b{kw}\b", re.IGNORECASE) 
            for kw in KEYWORDS["high"]
        ]
        self.medium_patterns = [
            re.compile(rf"\b{kw}\b", re.IGNORECASE)
            for kw in KEYWORDS["medium"]
        ]
        self.low_patterns = [
            re.compile(rf"\b{kw}\b", re.IGNORECASE)
            for kw in KEYWORDS["low"]
        ]
        self.negative_patterns = [
            re.compile(rf"\b{kw}\b", re.IGNORECASE)
            for kw in NEGATIVE_KEYWORDS
        ]
        self.plasma_patterns = [
            re.compile(rf"\b{kw}\b", re.IGNORECASE)
            for kw in PLASMA_PROTEINS
        ]
    
    def score_paper(self, paper: dict) -> float:
        """
        Calculate relevance score for a paper.
        Returns score between 0 and 1.
        """
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        
        score = 0.0
        
        # High relevance keywords: +0.2 each, max 0.6
        high_matches = sum(1 for p in self.high_patterns if p.search(text))
        score += min(high_matches * 0.2, 0.6)
        
        # Medium relevance: +0.1 each, max 0.2
        medium_matches = sum(1 for p in self.medium_patterns if p.search(text))
        score += min(medium_matches * 0.1, 0.2)
        
        # Low relevance: +0.05 each, max 0.1
        low_matches = sum(1 for p in self.low_patterns if p.search(text))
        score += min(low_matches * 0.05, 0.1)
        
        # Plasma proteins bonus: +0.15
        plasma_matches = sum(1 for p in self.plasma_patterns if p.search(text))
        if plasma_matches > 0:
            score += 0.15
        
        # Negative keywords penalty: -0.3 each
        negative_matches = sum(1 for p in self.negative_patterns if p.search(text))
        score -= negative_matches * 0.3
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))
    
    def categorize_paper(self, paper: dict) -> list[str]:
        """
        Assign categories to a paper based on content.
        """
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        categories = []
        
        category_keywords = {
            "metabolic_engineering": [
                "metabolic engineering", "metabolic pathway", "flux balance",
                "metabolic flux", "pathway engineering"
            ],
            "protein_expression": [
                "recombinant protein", "protein expression", "heterologous expression",
                "expression system", "protein production"
            ],
            "synthetic_biology": [
                "synthetic biology", "gene circuit", "genetic circuit",
                "cell factory", "bioproduction"
            ],
            "codon_optimization": [
                "codon optimization", "codon usage", "codon bias",
                "synonymous codon"
            ],
            "fermentation": [
                "fermentation", "bioreactor", "fed-batch", "continuous culture",
                "bioprocess"
            ],
            "strain_engineering": [
                "strain engineering", "genome engineering", "CRISPR",
                "gene knockout", "gene insertion"
            ],
            "plasma_proteins": PLASMA_PROTEINS,
            "computational_tools": [
                "machine learning", "deep learning", "prediction model",
                "computational", "algorithm", "software tool"
            ],
        }
        
        for category, keywords in category_keywords.items():
            for kw in keywords:
                if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                    categories.append(category)
                    break
        
        return categories
    
    def filter_papers(
        self,
        papers: list[dict],
        min_score: float = 0.2,
        max_papers: int = 30
    ) -> list[dict]:
        """
        Filter and rank papers by relevance.
        """
        scored_papers = []
        
        for paper in papers:
            score = self.score_paper(paper)
            
            if score >= min_score:
                paper["relevance_score"] = score
                paper["categories"] = self.categorize_paper(paper)
                scored_papers.append(paper)
        
        # Sort by score descending
        scored_papers.sort(key=lambda p: p["relevance_score"], reverse=True)
        
        # Return top papers
        result = scored_papers[:max_papers]
        
        logger.info(
            f"Filtered {len(papers)} papers to {len(result)} "
            f"(min_score={min_score})"
        )
        
        return result
