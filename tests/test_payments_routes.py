"""Tests for payment routes."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from app.store import eob_analyses, mark_checkout_pending, mark_paid, initialize_analysis_payment


# Test client
client = TestClient(app)

# Test data
TEST_ANALYSIS_ID = "test-analysis-123"
TEST_SESSION_ID = "cs_test_session123"
TEST_PRICE_ID = "price_test123"
TEST_EMAIL = "test@example.com"


@pytest.fixture(autouse=True)
def setup_test_analysis():
    """Setup test analysis before each test."""
    # Add a test analysis to the store
    eob_analyses[TEST_ANALYSIS_ID] = {
        "id": TEST_ANALYSIS_ID,
        "status": "unpaid",
    }
    initialize_analysis_payment(TEST_ANALYSIS_ID)
    yield
    # Cleanup
    if TEST_ANALYSIS_ID in eob_analyses:
        del eob_analyses[TEST_ANALYSIS_ID]


class TestCheckoutSessionCreation:
    """Test checkout session creation endpoint."""
    
    @patch('app.api.payments_routes.stripe.checkout.Session.create')
    def test_create_checkout_session_success(self, mock_stripe_create):
        """Test successful checkout session creation."""
        mock_session = Mock()
        mock_session.id = TEST_SESSION_ID
        mock_session.url = "https://checkout.stripe.com/test"
        mock_stripe_create.return_value = mock_session
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_PRICE_ID': TEST_PRICE_ID,
        }):
            response = client.post(
                "/api/payments/create-checkout-session",
                json={
                    "analysis_id": TEST_ANALYSIS_ID,
                    "origin": "http://localhost:3000",
                    "price_variant": "control",
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == TEST_SESSION_ID
        assert data["checkout_url"] == "https://checkout.stripe.com/test"
        assert data["price_variant"] == "control"
    
    def test_create_checkout_session_analysis_not_found(self):
        """Test checkout creation with non-existent analysis."""
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_PRICE_ID': TEST_PRICE_ID,
        }):
            response = client.post(
                "/api/payments/create-checkout-session",
                json={
                    "analysis_id": "non-existent-123",
                    "origin": "http://localhost:3000",
                }
            )
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"
    
    def test_create_checkout_session_invalid_analysis_id(self):
        """Test checkout creation with invalid analysis ID."""
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_PRICE_ID': TEST_PRICE_ID,
        }):
            response = client.post(
                "/api/payments/create-checkout-session",
                json={
                    "analysis_id": "",
                    "origin": "http://localhost:3000",
                }
            )
        
        assert response.status_code == 422  # Validation error


class TestPaymentStatus:
    """Test payment status endpoint."""
    
    def test_get_payment_status_unpaid(self):
        """Test getting status of unpaid analysis."""
        response = client.get(f"/api/payments/status/{TEST_ANALYSIS_ID}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unpaid"
        assert data["paid"] is False
        assert data["analysis_id"] == TEST_ANALYSIS_ID
    
    def test_get_payment_status_paid(self):
        """Test getting status of paid analysis."""
        # Mark as paid
        mark_paid(
            TEST_ANALYSIS_ID,
            session_id=TEST_SESSION_ID,
            amount_total=2999,
            customer_email=TEST_EMAIL,
            price_variant="control",
        )
        
        response = client.get(f"/api/payments/status/{TEST_ANALYSIS_ID}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paid"
        assert data["paid"] is True
        assert data["customer_email"] == TEST_EMAIL
        assert data["price_variant"] == "control"
    
    def test_get_payment_status_analysis_not_found(self):
        """Test getting status of non-existent analysis."""
        response = client.get(f"/api/payments/status/non-existent-123")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"


class TestPaymentHistory:
    """Test payment history endpoint."""
    
    def test_get_payment_history_empty(self):
        """Test getting payment history with no transactions."""
        response = client.get(f"/api/payments/history/{TEST_ANALYSIS_ID}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_id"] == TEST_ANALYSIS_ID
        assert "history" in data
        assert data["history"]["refunds"] == []
        assert data["history"]["failed_attempts"] == []
    
    def test_get_payment_history_analysis_not_found(self):
        """Test getting history of non-existent analysis."""
        response = client.get(f"/api/payments/history/non-existent-123")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"


class TestRefund:
    """Test refund endpoint."""
    
    def test_refund_unpaid_payment(self):
        """Test refunding an unpaid payment."""
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
        }):
            response = client.post(
                "/api/payments/refund",
                json={
                    "analysis_id": TEST_ANALYSIS_ID,
                    "reason": "Customer request",
                }
            )
        
        assert response.status_code == 400
        assert "only paid" in response.json()["detail"].lower()
    
    @patch('app.api.payments_routes.stripe.checkout.Session.retrieve')
    @patch('app.api.payments_routes.stripe.Refund.create')
    def test_refund_paid_payment_success(self, mock_refund_create, mock_session_retrieve):
        """Test successful refund of paid payment."""
        # First mark payment as paid
        mark_paid(
            TEST_ANALYSIS_ID,
            session_id=TEST_SESSION_ID,
            amount_total=2999,
            customer_email=TEST_EMAIL,
            price_variant="control",
        )
        
        # Setup mocks
        mock_session = Mock()
        mock_session.payment_intent = "pi_test123"
        mock_session_retrieve.return_value = mock_session
        
        mock_refund = Mock()
        mock_refund.id = "re_test123"
        mock_refund.status = "succeeded"
        mock_refund_create.return_value = mock_refund
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
        }):
            response = client.post(
                "/api/payments/refund",
                json={
                    "analysis_id": TEST_ANALYSIS_ID,
                    "reason": "Customer changed mind",
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["refund_id"] == "re_test123"
        assert data["analysis_id"] == TEST_ANALYSIS_ID
        assert data["status"] == "succeeded"
    
    def test_refund_invalid_reason_too_long(self):
        """Test refund with invalid reason (too long)."""
        mark_paid(
            TEST_ANALYSIS_ID,
            session_id=TEST_SESSION_ID,
            amount_total=2999,
        )
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
        }):
            response = client.post(
                "/api/payments/refund",
                json={
                    "analysis_id": TEST_ANALYSIS_ID,
                    "reason": "x" * 501,  # Too long
                }
            )
        
        assert response.status_code == 422  # Validation error


class TestWebhook:
    """Test webhook endpoint."""
    
    def test_webhook_missing_signature(self):
        """Test webhook without signature."""
        response = client.post(
            "/api/payments/webhook",
            json={"type": "checkout.session.completed"},
        )
        
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()
    
    @patch('app.api.payments_routes.stripe.Webhook.construct_event')
    def test_webhook_invalid_signature(self, mock_construct_event):
        """Test webhook with invalid signature."""
        mock_construct_event.side_effect = Exception("Invalid signature")
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_WEBHOOK_SECRET': 'webhook_secret',
        }):
            response = client.post(
                "/api/payments/webhook",
                json={},
                headers={"stripe-signature": "invalid_sig"},
            )
        
        assert response.status_code == 400
    
    @patch('app.api.payments_routes.stripe.Webhook.construct_event')
    def test_webhook_checkout_completed(self, mock_construct_event):
        """Test webhook for checkout completion."""
        mock_event = {
            "id": "evt_test123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": TEST_SESSION_ID,
                    "metadata": {
                        "analysis_id": TEST_ANALYSIS_ID,
                        "price_variant": "control",
                    },
                    "customer_details": {
                        "email": TEST_EMAIL,
                    },
                    "amount_total": 2999,
                }
            }
        }
        mock_construct_event.return_value = mock_event
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_WEBHOOK_SECRET': 'webhook_secret',
        }):
            response = client.post(
                "/api/payments/webhook",
                json={},
                headers={"stripe-signature": "valid_sig"},
            )
        
        assert response.status_code == 200
        assert response.json()["received"] is True
    
    @patch('app.api.payments_routes.stripe.Webhook.construct_event')
    def test_webhook_duplicate_event(self, mock_construct_event):
        """Test that duplicate webhook events are handled correctly."""
        mock_event = {
            "id": "evt_duplicate123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": TEST_SESSION_ID,
                    "metadata": {
                        "analysis_id": TEST_ANALYSIS_ID,
                        "price_variant": "control",
                    },
                    "customer_details": {"email": TEST_EMAIL},
                    "amount_total": 2999,
                }
            }
        }
        mock_construct_event.return_value = mock_event
        
        with patch.dict('os.environ', {
            'STRIPE_SECRET_KEY': 'test_key',
            'STRIPE_WEBHOOK_SECRET': 'webhook_secret',
        }):
            # First webhook
            response1 = client.post(
                "/api/payments/webhook",
                json={},
                headers={"stripe-signature": "sig1"},
            )
            
            # Duplicate webhook
            response2 = client.post(
                "/api/payments/webhook",
                json={},
                headers={"stripe-signature": "sig2"},
            )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        # Both should be received
        assert response1.json()["received"] is True
        assert response2.json()["received"] is True


class TestHealthCheck:
    """Test health check endpoint."""
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
