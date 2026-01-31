"""
Email sending with multiple provider support.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from loguru import logger

from app.config import settings
from app.email.templates import render_digest, render_plain_text


class EmailSender:
    """Send emails via configured provider."""
    
    def __init__(self):
        self.provider = settings.email_provider
        logger.info(f"Email provider: {self.provider}")
    
    async def send_digest(
        self,
        papers: list[dict],
        subscriber_email: str,
        subscriber_name: str = None,
        unsubscribe_token: str = None,
    ) -> bool:
        """
        Send digest email to a subscriber.
        """
        # Render templates
        html_content = render_digest(
            papers=papers,
            subscriber_name=subscriber_name,
            subscriber_email=subscriber_email,
            unsubscribe_token=unsubscribe_token,
        )
        text_content = render_plain_text(papers)
        
        subject = f"🧬 SynBio Digest: {len(papers)} nieuwe papers deze week"
        
        return await self._send(
            to_email=subscriber_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    
    async def _send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """
        Send email via configured provider.
        """
        if self.provider == "console":
            return self._send_console(to_email, subject, text_content)
        elif self.provider == "resend":
            return await self._send_resend(to_email, subject, html_content, text_content)
        elif self.provider == "smtp":
            return self._send_smtp(to_email, subject, html_content, text_content)
        else:
            logger.error(f"Unknown email provider: {self.provider}")
            return False
    
    def _send_console(
        self,
        to_email: str,
        subject: str,
        text_content: str,
    ) -> bool:
        """Print email to console (for testing)."""
        logger.info(f"\n{'='*60}")
        logger.info(f"TO: {to_email}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"{'='*60}")
        logger.info(text_content[:1000])
        logger.info(f"{'='*60}\n")
        return True
    
    async def _send_resend(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send via Resend API."""
        try:
            import resend
            resend.api_key = settings.resend_api_key
            
            params = {
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Resend email sent to {to_email}: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Resend error: {e}")
            return False
    
    def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send via SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.email_from
            msg["To"] = to_email
            
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(
                    settings.smtp_user,
                    to_email,
                    msg.as_string()
                )
            
            logger.info(f"SMTP email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False
    
    async def send_to_all_subscribers(
        self,
        papers: list[dict],
        subscribers: list[dict],
    ) -> dict:
        """
        Send digest to all subscribers.
        Returns stats.
        """
        success = 0
        failed = 0
        
        for sub in subscribers:
            result = await self.send_digest(
                papers=papers,
                subscriber_email=sub["email"],
                subscriber_name=sub.get("name"),
                unsubscribe_token=sub.get("unsubscribe_token"),
            )
            
            if result:
                success += 1
            else:
                failed += 1
        
        logger.info(f"Sent digest: {success} success, {failed} failed")
        
        return {
            "success": success,
            "failed": failed,
            "total": len(subscribers),
        }
