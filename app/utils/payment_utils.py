"""Payment processing utilities and retry logic."""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


class PaymentError(Exception):
    """Base exception for payment errors."""
    
    def __init__(self, message: str, error_code: str | None = None, is_transient: bool = False):
        self.message = message
        self.error_code = error_code
        self.is_transient = is_transient
        super().__init__(message)


class TransientPaymentError(PaymentError):
    """Transient payment error that can be retried."""
    
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message, error_code, is_transient=True)


class PermanentPaymentError(PaymentError):
    """Permanent payment error that should not be retried."""
    
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message, error_code, is_transient=False)


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    *args,
    **kwargs
) -> T:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        *args: Arguments to pass to func
        **kwargs: Keyword arguments to pass to func
    
    Returns:
        Result from func
    
    Raises:
        PermanentPaymentError: If error is permanent (should not retry)
        PaymentError: If max retries exceeded
    """
    delay = base_delay
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"Attempt {attempt + 1}/{max_retries + 1} for {func.__name__}")
            return await func(*args, **kwargs)
        except PermanentPaymentError as e:
            logger.error(f"Permanent error in {func.__name__}: {e.message}")
            raise
        except (TransientPaymentError, PaymentError) as e:
            if not e.is_transient:
                logger.error(f"Non-transient error in {func.__name__}: {e.message}")
                raise
            
            if attempt < max_retries:
                logger.warning(
                    f"Transient error in {func.__name__} (attempt {attempt + 1}): {e.message}. "
                    f"Retrying in {delay}s..."
                )
                last_error = e
                await asyncio.sleep(delay)
                # Exponential backoff with jitter
                delay = min(delay * 2 + (0.1 * (attempt + 1)), max_delay)
            else:
                logger.error(f"Max retries exceeded for {func.__name__}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                raise
    
    raise PaymentError(f"Failed to execute {func.__name__} after {max_retries + 1} attempts")


def classify_stripe_error(error: Exception) -> tuple[bool, str]:
    """
    Classify Stripe error as transient or permanent.
    
    Returns:
        Tuple of (is_transient, error_code)
    """
    error_str = str(error).lower()
    error_code = getattr(error, 'http_status', None)
    
    # Transient errors that can be retried
    transient_indicators = [
        'timeout',
        'connection error',
        'rate_limit',
        'temporarily_unavailable',
        'service_unavailable',
    ]
    
    if any(indicator in error_str for indicator in transient_indicators):
        return True, 'transient_stripe_error'
    
    # HTTP status codes indicating transient errors
    if error_code in [429, 500, 502, 503, 504]:
        return True, f'transient_{error_code}'
    
    return False, 'permanent_stripe_error'


def is_within_window(timestamp_iso: str, window_seconds: int = 3600) -> bool:
    """Check if a timestamp is within the specified window from now."""
    try:
        timestamp = datetime.fromisoformat(timestamp_iso)
        return datetime.utcnow() <= timestamp + timedelta(seconds=window_seconds)
    except (ValueError, TypeError):
        return False


def format_amount_for_display(amount_cents: int) -> str:
    """Format amount in cents as dollars string."""
    return f"${amount_cents / 100:.2f}"
