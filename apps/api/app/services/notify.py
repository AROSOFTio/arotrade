"""In-app notifications plus optional email delivery.

Email silently no-ops when SMTP is not configured so callers never need to
care whether the mail server exists.
"""

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app import models
from app.config import settings

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    category: str = "general",
    link: str | None = None,
) -> models.Notification:
    """Persist an in-app notification. Caller is responsible for db.commit()."""
    notification = models.Notification(
        user_id=user_id,
        title=title[:255],
        body=body,
        category=category,
        link=link,
    )
    db.add(notification)
    return notification


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email if SMTP is configured. Returns True on success."""
    if not settings.SMTP_HOST:
        return False

    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except Exception as exc:
        logger.warning("Email delivery failed for %s: %s", to_email, exc)
        return False


def notify_signal_event(db: Session, user: models.User, signal: models.Signal, event: str) -> None:
    """Create the in-app notification (and best-effort email) for a signal event."""
    direction = signal.signal_type.upper()
    titles = {
        "created": f"New {direction} signal: {signal.symbol}",
        "approved": f"Signal approved: {signal.symbol} {direction}",
        "executed_demo": f"Paper trade opened: {signal.symbol} {direction}",
        "executed_live": f"LIVE trade opened: {signal.symbol} {direction}",
    }
    title = titles.get(event, f"Signal update: {signal.symbol}")
    body = (
        f"{signal.symbol} {signal.timeframe} {direction} | entry {signal.entry_min}-{signal.entry_max} "
        f"| SL {signal.stop_loss} | TP {signal.take_profit_1 or '-'} | confidence {signal.confidence}%"
    )
    create_notification(db, user.id, title, body, category="signal", link="/dashboard/signals")

    if event in ("approved", "executed_live"):
        send_email(user.email, f"AroTrade: {title}", f"{body}\n\nOpen your dashboard: {settings.APP_URL}/dashboard/signals")
