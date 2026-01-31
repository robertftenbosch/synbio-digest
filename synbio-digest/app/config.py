"""
Configuration management using Pydantic Settings.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///synbio_digest.db"
    
    # Email provider
    email_provider: str = "resend"  # resend, smtp, or console (for testing)
    
    # Resend
    resend_api_key: Optional[str] = None
    
    # SMTP
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    
    # Sender info
    email_from: str = "SynBio Digest <digest@yourdomain.com>"
    
    # OpenAI (optional, for better summaries)
    openai_api_key: Optional[str] = None
    
    # Search settings
    search_queries: list[str] = [
        "metabolic engineering",
        "synthetic biology pathway",
        "recombinant protein expression",
        "codon optimization",
        "metabolic flux analysis",
        "cell factory",
        "heterologous expression",
        "protein production E. coli",
        "yeast synthetic biology",
    ]
    
    # How many days back to search
    lookback_days: int = 7
    
    # Max papers per source
    max_papers_per_source: int = 50
    
    # Schedule (cron-style)
    digest_day: str = "mon"  # mon, tue, wed, thu, fri, sat, sun
    digest_hour: int = 7
    digest_minute: int = 0
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
