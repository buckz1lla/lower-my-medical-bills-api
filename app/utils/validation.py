"""Payment validation utilities."""

import re
from typing import Optional


def is_valid_email(email: str | None) -> bool:
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    
    # RFC 5322 simplified email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None


def sanitize_email(email: str | None) -> str | None:
    """Sanitize and validate email."""
    if not email:
        return None
    
    sanitized = email.strip().lower()
    if is_valid_email(sanitized):
        return sanitized
    return None


def validate_amount(amount: int | None) -> bool:
    """Validate payment amount is reasonable (in cents)."""
    if amount is None:
        return False
    # Amount should be positive and reasonable (between 1 cent and 1 million dollars)
    return 1 <= amount <= 100_000_000


def validate_stripe_price_id(price_id: str) -> bool:
    """Validate Stripe price ID format."""
    if not price_id:
        return False
    # Stripe price IDs start with 'price_' followed by alphanumeric characters
    return price_id.startswith('price_') and len(price_id) > 6


def validate_stripe_session_id(session_id: str) -> bool:
    """Validate Stripe session ID format."""
    if not session_id:
        return False
    # Stripe checkout session IDs start with 'cs_' followed by alphanumeric characters
    return session_id.startswith('cs_') and len(session_id) > 3


def validate_stripe_event_id(event_id: str) -> bool:
    """Validate Stripe event ID format."""
    if not event_id:
        return False
    # Stripe event IDs start with 'evt_' followed by alphanumeric characters
    return event_id.startswith('evt_') and len(event_id) > 4
