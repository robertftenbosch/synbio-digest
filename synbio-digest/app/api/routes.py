"""
API routes for subscription management.
"""
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscriber, get_db

router = APIRouter(prefix="/api", tags=["subscriptions"])


class SubscribeRequest(BaseModel):
    email: EmailStr
    name: str = None
    interests: list[str] = []


class SubscribeResponse(BaseModel):
    success: bool
    message: str


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    request: SubscribeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Subscribe to the weekly digest."""
    
    # Check if already subscribed
    result = await db.execute(
        select(Subscriber).where(Subscriber.email == request.email)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        if existing.confirmed:
            return SubscribeResponse(
                success=True,
                message="Je bent al ingeschreven!"
            )
        else:
            # Resend confirmation
            return SubscribeResponse(
                success=True,
                message="Check je email voor de bevestigingslink."
            )
    
    # Create new subscriber
    subscriber = Subscriber(
        email=request.email,
        name=request.name,
        interests=request.interests or [],
        confirmation_token=secrets.token_urlsafe(32),
        unsubscribe_token=secrets.token_urlsafe(32),
        confirmed=True,  # For MVP, skip email confirmation
    )
    
    db.add(subscriber)
    await db.commit()
    
    return SubscribeResponse(
        success=True,
        message="Welkom! Je ontvangt elke maandag de SynBio Digest."
    )


@router.get("/unsubscribe")
async def unsubscribe(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe from the digest."""
    
    result = await db.execute(
        select(Subscriber).where(Subscriber.unsubscribe_token == token)
    )
    subscriber = result.scalar_one_or_none()
    
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    await db.delete(subscriber)
    await db.commit()
    
    return {"success": True, "message": "Je bent uitgeschreven."}


@router.get("/subscribers/count")
async def get_subscriber_count(
    db: AsyncSession = Depends(get_db),
):
    """Get total subscriber count (public metric)."""
    
    result = await db.execute(
        select(Subscriber).where(Subscriber.confirmed == True)
    )
    subscribers = result.scalars().all()
    
    return {"count": len(subscribers)}


# Simple landing page HTML
LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SynBio Weekly Digest</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 { 
            color: #0d9488; 
            margin-top: 0;
        }
        p { color: #4b5563; }
        form { margin-top: 24px; }
        input[type="email"], input[type="text"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 16px;
            margin-bottom: 12px;
        }
        input:focus {
            outline: none;
            border-color: #0d9488;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #0d9488;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover { background: #0f766e; }
        .features {
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e5e7eb;
        }
        .feature {
            display: flex;
            align-items: start;
            margin-bottom: 16px;
        }
        .feature-icon {
            font-size: 24px;
            margin-right: 12px;
        }
        .success {
            background: #d1fae5;
            color: #065f46;
            padding: 16px;
            border-radius: 8px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>🧬 SynBio Weekly Digest</h1>
        <p>
            Elke maandag de belangrijkste papers over metabolic engineering, 
            synthetische biologie en recombinant protein production in je inbox.
        </p>
        
        <div id="success" class="success">
            ✅ Welkom! Je ontvangt elke maandag de digest.
        </div>
        
        <form id="subscribe-form">
            <input type="email" name="email" placeholder="je@email.com" required>
            <input type="text" name="name" placeholder="Je naam (optioneel)">
            <button type="submit">Schrijf me in</button>
        </form>
        
        <div class="features">
            <div class="feature">
                <span class="feature-icon">📚</span>
                <div>
                    <strong>Gecureerde selectie</strong><br>
                    Alleen de meest relevante papers uit PubMed, bioRxiv en arXiv
                </div>
            </div>
            <div class="feature">
                <span class="feature-icon">⭐</span>
                <div>
                    <strong>Relevantie scores</strong><br>
                    We scoren papers op relevantie voor metabolic engineering
                </div>
            </div>
            <div class="feature">
                <span class="feature-icon">📝</span>
                <div>
                    <strong>Samenvattingen</strong><br>
                    Korte samenvattingen zodat je snel kunt scannen
                </div>
            </div>
        </div>
    </div>
    
    <script>
        document.getElementById('subscribe-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const data = {
                email: form.email.value,
                name: form.name.value || null
            };
            
            const response = await fetch('/api/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            if (response.ok) {
                document.getElementById('success').style.display = 'block';
                form.style.display = 'none';
            }
        });
    </script>
</body>
</html>
"""


@router.get("/", include_in_schema=False)
async def landing_page():
    """Serve the landing page."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=LANDING_PAGE_HTML)
