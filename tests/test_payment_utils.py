"""Tests for payment utilities."""

import asyncio
import pytest
from app.utils.payment_utils import (
    PaymentError,
    TransientPaymentError,
    PermanentPaymentError,
    classify_stripe_error,
    is_within_window,
    format_amount_for_display,
    retry_with_backoff,
)
from datetime import datetime, timedelta


class TestPaymentErrors:
    """Test payment error classes."""
    
    def test_payment_error_creation(self):
        """Test creating PaymentError."""
        error = PaymentError("Test error", error_code="test_code", is_transient=False)
        assert error.message == "Test error"
        assert error.error_code == "test_code"
        assert error.is_transient is False
    
    def test_transient_payment_error(self):
        """Test TransientPaymentError."""
        error = TransientPaymentError("Timeout", error_code="timeout")
        assert error.is_transient is True
        assert error.error_code == "timeout"
    
    def test_permanent_payment_error(self):
        """Test PermanentPaymentError."""
        error = PermanentPaymentError("Auth failed", error_code="auth_error")
        assert error.is_transient is False
        assert error.error_code == "auth_error"


class TestStripeErrorClassification:
    """Test Stripe error classification."""
    
    def test_classify_transient_errors(self):
        """Test classification of transient errors."""
        transient_keywords = ["timeout", "connection error", "rate_limit", "temporarily_unavailable"]
        
        class MockError(Exception):
            pass
        
        for keyword in transient_keywords:
            error = MockError(keyword)
            is_transient, code = classify_stripe_error(error)
            assert is_transient is True, f"Should classify {keyword} as transient"
    
    def test_classify_permanent_errors(self):
        """Test classification of permanent errors."""
        class MockError(Exception):
            pass
        
        error = MockError("Invalid API key")
        is_transient, code = classify_stripe_error(error)
        assert is_transient is False
    
    def test_classify_by_http_status(self):
        """Test classification by HTTP status code."""
        class MockError(Exception):
            http_status = None
        
        # Transient status codes
        for status in [429, 500, 502, 503, 504]:
            error = MockError("error")
            error.http_status = status
            is_transient, code = classify_stripe_error(error)
            assert is_transient is True, f"Status {status} should be transient"
        
        # Permanent status codes
        for status in [400, 401, 404]:
            error = MockError("error")
            error.http_status = status
            is_transient, code = classify_stripe_error(error)
            assert is_transient is False, f"Status {status} should be permanent"


class TestTimeWindow:
    """Test time window validation."""
    
    def test_within_window(self):
        """Test timestamp within window."""
        now = datetime.utcnow()
        iso_string = now.isoformat()
        assert is_within_window(iso_string, window_seconds=60) is True
    
    def test_outside_window(self):
        """Test timestamp outside window."""
        past = datetime.utcnow() - timedelta(seconds=120)
        iso_string = past.isoformat()
        assert is_within_window(iso_string, window_seconds=60) is False
    
    def test_invalid_timestamp(self):
        """Test invalid timestamp."""
        assert is_within_window("invalid", window_seconds=60) is False
        assert is_within_window(None, window_seconds=60) is False


class TestAmountFormatting:
    """Test amount formatting."""
    
    def test_format_amount_for_display(self):
        """Test formatting amounts as dollars."""
        assert format_amount_for_display(0) == "$0.00"
        assert format_amount_for_display(99) == "$0.99"
        assert format_amount_for_display(2999) == "$29.99"
        assert format_amount_for_display(100000) == "$1000.00"
        assert format_amount_for_display(100_000_000) == "$1000000.00"


@pytest.mark.asyncio
class TestRetryWithBackoff:
    """Test retry with backoff functionality."""
    
    async def test_successful_on_first_try(self):
        """Test successful execution on first try."""
        call_count = 0
        
        async def success_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_with_backoff(success_func, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 1
    
    async def test_retry_transient_error(self):
        """Test retry on transient errors."""
        call_count = 0
        
        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransientPaymentError("Timeout")
            return "success"
        
        result = await retry_with_backoff(flaky_func, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 3
    
    async def test_permanent_error_no_retry(self):
        """Test that permanent errors are not retried."""
        call_count = 0
        
        async def permanent_fail_func() -> str:
            nonlocal call_count
            call_count += 1
            raise PermanentPaymentError("Auth failed")
        
        with pytest.raises(PermanentPaymentError):
            await retry_with_backoff(permanent_fail_func, max_retries=3, base_delay=0.01)
        
        assert call_count == 1
    
    async def test_max_retries_exceeded(self):
        """Test that error is raised after max retries."""
        async def always_fail_func() -> str:
            raise TransientPaymentError("Always fails")
        
        with pytest.raises(PaymentError):
            await retry_with_backoff(
                always_fail_func,
                max_retries=2,
                base_delay=0.01,
                max_delay=0.02
            )
