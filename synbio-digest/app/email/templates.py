"""
Email template rendering.
"""
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


# Setup Jinja2
template_dir = Path(__file__).parent.parent.parent / "templates"
env = Environment(loader=FileSystemLoader(template_dir))


def render_digest(
    papers: list[dict],
    subscriber_name: str = None,
    subscriber_email: str = None,
    unsubscribe_token: str = None,
) -> str:
    """
    Render the digest email template.
    """
    template = env.get_template("digest.html")
    
    # Split papers into top and other
    top_papers = [p for p in papers if p.get("relevance_score", 0) >= 0.5][:5]
    other_papers = [p for p in papers if p not in top_papers][:10]
    
    # Count sources
    sources = set(p["source"] for p in papers)
    
    # High relevance count
    high_relevance_count = len([p for p in papers if p.get("relevance_score", 0) >= 0.5])
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    date_range = f"{start_date:%d %b} - {end_date:%d %b %Y}"
    
    # URLs
    base_url = "https://yourdomain.com"  # Update this
    
    return template.render(
        papers=papers,
        top_papers=top_papers,
        other_papers=other_papers,
        sources=sources,
        high_relevance_count=high_relevance_count,
        date_range=date_range,
        subscriber_name=subscriber_name,
        website_url=base_url,
        unsubscribe_url=f"{base_url}/unsubscribe?token={unsubscribe_token or ''}",
        preferences_url=f"{base_url}/preferences?email={subscriber_email or ''}",
    )


def render_plain_text(papers: list[dict]) -> str:
    """
    Render a plain text version of the digest.
    """
    lines = [
        "🧬 SynBio Weekly Digest",
        "=" * 40,
        "",
        f"Deze week: {len(papers)} relevante papers",
        "",
    ]
    
    for i, paper in enumerate(papers[:15], 1):
        score = int(paper.get("relevance_score", 0) * 100)
        lines.extend([
            f"{i}. {paper['title']}",
            f"   Bron: {paper['source']} | Relevantie: {score}%",
            f"   {paper.get('summary', '')[:200]}...",
            f"   Link: {paper['url']}",
            "",
        ])
    
    lines.extend([
        "-" * 40,
        "Uitschrijven: reply met 'unsubscribe'",
    ])
    
    return "\n".join(lines)
