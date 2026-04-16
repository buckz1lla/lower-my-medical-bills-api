"""Tests for payment validation utilities."""

import pytest
from app.utils.validation import (
    is_valid_email,
    sanitize_email,
    validate_amount,
    validate_stripe_price_id,
    validate_stripe_session_id,
    validate_stripe_event_id,
)


class TestEmailValidation:
    """Test email validation functions."""
    
    def test_valid_emails(self):
        """Test that valid emails are accepted."""
        valid_emails = [
            "user@example.com",
            "john.doe@company.co.uk",
            "test+tag@domain.com",
            "a@b.co",
        ]
        for email in valid_emails:
            assert is_valid_email(email), f"Should accept {email}"
    
    def test_invalid_emails(self):
        """Test that invalid emails are rejected."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user @example.com",
            "user@example",
            "",
            None,
        ]
        for email in invalid_emails:
            assert not is_valid_email(email), f"Should reject {email}"
    
    def test_sanitize_email_valid(self):
        """Test email sanitization for valid emails."""
        assert sanitize_email("User@Example.COM") == "user@example.com"
        assert sanitize_email("  test@domain.com  ") == "test@domain.com"
    
    def test_sanitize_email_invalid(self):
        """Test email sanitization returns None for invalid emails."""
        assert sanitize_email("notanemail") is None
        assert sanitize_email(None) is None
        assert sanitize_email("") is None


class TestAmountValidation:
    """Test payment amount validation."""
    
    def test_valid_amounts(self):
        """Test that valid amounts are accepted."""
        valid_amounts = [
            1,           # $0.01
            99,          # $0.99
            2999,        # $29.99
            100000,      # $1,000.00
            100_000_000, # $1,000,000.00
        ]
        for amount in valid_amounts:
            assert validate_amount(amount), f"Should accept {amount}"
    
    def test_invalid_amounts(self):
        """Test that invalid amounts are rejected."""
        invalid_amounts = [
            0,           # Too low
            -100,        # Negative
            100_000_001, # Too high
            None,
        ]
        for amount in invalid_amounts:
            assert not validate_amount(amount), f"Should reject {amount}"


class TestStripeIdValidation:
    """Test Stripe ID validation functions."""
    
    def test_price_id_valid(self):
        """Test valid price IDs."""
        assert validate_stripe_price_id("price_1234567890")
        assert validate_stripe_price_id("price_abc123XYZ")
    
    def test_price_id_invalid(self):
        """Test invalid price IDs."""
        assert not validate_stripe_price_id("prc_123")
        assert not validate_stripe_price_id("123")
        assert not validate_stripe_price_id("")
        assert not validate_stripe_price_id(None)
    
    def test_session_id_valid(self):
        """Test valid session IDs."""
        assert validate_stripe_session_id("cs_test_123abc")
        assert validate_stripe_session_id("cs_1234567890abcdef")
    
    def test_session_id_invalid(self):
        """Test invalid session IDs."""
        assert not validate_stripe_session_id("cs_")
        assert not validate_stripe_session_id("ch_123")
        assert not validate_stripe_session_id("")
        assert not validate_stripe_session_id(None)
    
    def test_event_id_valid(self):
        """Test valid event IDs."""
        assert validate_stripe_event_id("evt_1234567890")
        assert validate_stripe_event_id("evt_test_abc123")
    
    def test_event_id_invalid(self):
        """Test invalid event IDs."""
        assert not validate_stripe_event_id("evt_")
        assert not validate_stripe_event_id("event_123")
        assert not validate_stripe_event_id("")
        assert not validate_stripe_event_id(None)
