"""Payment processing routes with comprehensive error handling, validation, and tracking."""

import logging
import os
from datetime import datetime

import stripe
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from app.api.analytics_routes import AnalyticsEvent, log_event_to_file
from app.store import (
    checkout_session_to_analysis,
    eob_analyses,
    mark_checkout_pending,
    mark_paid,
    payment_status_by_analysis,
    record_webhook_event,
    record_refund,
    record_failed_payment_attempt,
    get_payment_history,
)
from app.utils.validation import (
    is_valid_email,
    sanitize_email,
    validate_amount,
    validate_stripe_price_id,
    validate_stripe_session_id,
    validate_stripe_event_id,
)
from app.utils.payment_utils import (
    PaymentError,
    TransientPaymentError,
    PermanentPaymentError,
    classify_stripe_error,
    format_amount_for_display,
)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if os.getenv("DEBUG") == "true" else logging.INFO)

router = APIRouter()

# Configuration constants
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
EXPECTED_PRICE_CENTS = {
    "control": 2999,  # $29.99
    "test": 99,       # $0.99
}


class CheckoutSessionRequest(BaseModel):
    """Request to create a checkout session."""
    analysis_id: str
    origin: str | None = None
    price_variant: str | None = None
    
    @field_validator("analysis_id")
    @classmethod
    def validate_analysis_id(cls, v):
        if not v or not isinstance(v, str) or len(v) < 1:
            raise ValueError("Invalid analysis_id")
        return v


class RefundRequest(BaseModel):
    """Request to refund a payment."""
    analysis_id: str
    reason: str | None = None
    
    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v):
        if v and len(v) > 500:
            raise ValueError("Reason must be less than 500 characters")
        return v


def _require_env(name: str) -> str:
    """Get and validate a required environment variable."""
    value = os.getenv(name, "").strip()
    if not value:
        logger.error(f"Missing required environment variable: {name}")
        raise HTTPException(status_code=500, detail=f"Server configuration error")
    return value


def _frontend_origin(request_origin: str | None) -> str:
    """Determine the frontend origin URL."""
    env_origin = os.getenv("FRONTEND_URL", "").strip()
    origin = request_origin or env_origin or "http://localhost:3000"
    origin = origin.rstrip("/")
    
    # Basic validation of origin
    if not origin.startswith(("http://", "https://")):
        logger.warning(f"Invalid origin format: {origin}")
        origin = "http://localhost:3000"
    
    return origin


def _configure_stripe() -> None:
    """Configure Stripe API with secret key."""
    api_key = _require_env("STRIPE_SECRET_KEY")
    stripe.api_key = api_key
    stripe.max_network_retries = MAX_RETRIES


def _extract_customer_email(session_obj: dict | object | None) -> str | None:
    """Extract and validate customer email from Stripe session object."""
    if not session_obj:
        return None

    email = None
    
    if isinstance(session_obj, dict):
        details = session_obj.get("customer_details", {}) or {}
        email = details.get("email") or session_obj.get("customer_email")
    else:
        details = getattr(session_obj, "customer_details", None) or {}
        email = (
            details.get("email") if isinstance(details, dict) 
            else getattr(session_obj, "customer_email", None)
        )
    
    # Sanitize and validate email
    validated_email = sanitize_email(email)
    if validated_email and is_valid_email(validated_email):
        return validated_email
    
    logger.warning(f"Invalid email extracted from session: {email}")
    return None


def _log_payment_event(
    event_type: str,
    analysis_id: str,
    amount_total: int | None = None,
    customer_email: str | None = None,
    price_variant: str | None = None,
    error: str | None = None,
) -> None:
    """Log payment event to analytics."""
    try:
        amount_dollars = round((amount_total or 2999) / 100, 2) if amount_total else None
        
        event_data = {
            "analysisId": analysis_id,
            "price_variant": price_variant or "control",
        }
        
        if amount_dollars is not None:
            event_data["amount"] = amount_dollars
        
        if customer_email:
            event_data["customer_email"] = customer_email
        
        if error:
            event_data["error"] = error
        
        log_event_to_file(
            AnalyticsEvent(
                event=event_type,
                data=event_data,
                timestamp=datetime.utcnow().isoformat(),
            )
        )
    except Exception as e:
        logger.error(f"Failed to log payment event: {str(e)}")


def _mark_paid_and_track(
    analysis_id: str,
    session_id: str | None = None,
    amount_total: int | None = None,
    customer_email: str | None = None,
    price_variant: str | None = None,
) -> dict:
    """Mark an analysis as paid and log the event."""
    try:
        record, should_log = mark_paid(
            analysis_id,
            session_id=session_id,
            amount_total=amount_total,
            customer_email=customer_email,
            price_variant=price_variant,
        )
        
        if should_log:
            _log_payment_event(
                "payment_completed",
                analysis_id,
                amount_total,
                customer_email,
                price_variant,
            )
            logger.info(
                f"Payment recorded for analysis {analysis_id}: "
                f"amount={format_amount_for_display(amount_total or 0)}"
            )
        
        return record
    except Exception as e:
        logger.error(f"Failed to mark payment: {str(e)}")
        raise


def _price_id_for_variant(variant: str | None) -> tuple[str, str]:
    """Get Stripe price ID for the given variant."""
    normalized = (variant or "control").strip().lower()
    
    if normalized == "test":
        test_price_id = os.getenv("STRIPE_PRICE_ID_TEST", "").strip()
        if test_price_id and validate_stripe_price_id(test_price_id):
            logger.debug("Using test price ID")
            return test_price_id, "test"
        logger.warning("Invalid or missing test price ID, falling back to control")
    
    control_price_id = (
        os.getenv("STRIPE_PRICE_ID_CONTROL", "").strip() 
        or _require_env("STRIPE_PRICE_ID")
    )
    
    if not validate_stripe_price_id(control_price_id):
        logger.error(f"Invalid Stripe price ID format: {control_price_id}")
        raise HTTPException(status_code=500, detail="Server configuration error")
    
    return control_price_id, "control"


def _validate_session_amount(
    session_obj: dict | object,
    expected_variant: str,
) -> bool:
    """Validate that session amount matches expected price for variant."""
    amount = getattr(session_obj, "amount_total", None) or session_obj.get("amount_total")
    
    if amount is None:
        logger.warning(f"Session has no amount_total")
        return False
    
    expected_amount = EXPECTED_PRICE_CENTS.get(expected_variant)
    
    if amount != expected_amount:
        logger.warning(
            f"Amount mismatch for variant {expected_variant}: "
            f"received {format_amount_for_display(amount)}, "
            f"expected {format_amount_for_display(expected_amount or 0)}"
        )
        # Don't fail hard on amount mismatch, just log it
        return False
    
    return True


@router.post("/payments/create-checkout-session")
async def create_checkout_session(payload: CheckoutSessionRequest):
    """Create a Stripe checkout session for payment."""
    logger.info(f"Creating checkout session for analysis {payload.analysis_id}")
    
    # Validate analysis exists
    if payload.analysis_id not in eob_analyses:
        logger.warning(f"Analysis not found: {payload.analysis_id}")
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    try:
        _configure_stripe()
        price_id, variant = _price_id_for_variant(payload.price_variant)
        origin = _frontend_origin(payload.origin)
        
        logger.debug(
            f"Stripe session params: price_id={price_id}, variant={variant}, origin={origin}"
        )
        
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=(
                    f"{origin}/results/{payload.analysis_id}"
                    "?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
                ),
                cancel_url=f"{origin}/results/{payload.analysis_id}?payment=cancelled",
                metadata={
                    "analysis_id": payload.analysis_id,
                    "price_variant": variant,
                },
                payment_intent_data={
                    "metadata": {
                        "analysis_id": payload.analysis_id,
                        "price_variant": variant,
                    }
                },
                timeout=REQUEST_TIMEOUT,
            )
        except stripe.error.RateLimitError as e:
            logger.error(f"Stripe rate limit exceeded: {str(e)}")
            raise TransientPaymentError(
                "Service temporarily unavailable",
                error_code="rate_limit"
            )
        except stripe.error.AuthenticationError as e:
            logger.error(f"Stripe authentication failed: {str(e)}")
            raise PermanentPaymentError(
                "Payment service error",
                error_code="auth_error"
            )
        except stripe.error.StripeError as e:
            is_transient, error_code = classify_stripe_error(e)
            error_type = TransientPaymentError if is_transient else PermanentPaymentError
            logger.error(f"Stripe error ({error_code}): {str(e)}")
            raise error_type(f"Payment service error: {str(e)}", error_code)
        
        # Mark checkout as pending
        mark_checkout_pending(payload.analysis_id, session.id, variant)
        
        _log_payment_event(
            "checkout_session_created",
            payload.analysis_id,
            price_variant=variant,
        )
        
        logger.info(
            f"Checkout session created: {session.id} for analysis {payload.analysis_id}"
        )
        
        return {
            "session_id": session.id,
            "checkout_url": session.url,
            "price_variant": variant,
        }
    
    except (TransientPaymentError, PermanentPaymentError):
        raise HTTPException(status_code=500, detail="Payment service error")
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/payments/status/{analysis_id}")
async def get_payment_status(analysis_id: str, session_id: str | None = Query(None)):
    """Get payment status for an analysis."""
    logger.debug(f"Checking payment status for {analysis_id}")
    
    if analysis_id not in eob_analyses:
        logger.warning(f"Analysis not found: {analysis_id}")
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    record = payment_status_by_analysis.get(analysis_id, {"status": "unpaid"})
    
    # If payment isn't marked as complete, try to sync with Stripe
    if record.get("status") != "paid" and session_id:
        if not validate_stripe_session_id(session_id):
            logger.warning(f"Invalid session ID format: {session_id}")
            return {
                "analysis_id": analysis_id,
                "status": record.get("status", "unpaid"),
                "paid": record.get("status") == "paid",
                "checkout_session_id": record.get("checkout_session_id"),
                "paid_at": record.get("paid_at"),
                "customer_email": record.get("customer_email"),
                "price_variant": record.get("price_variant"),
            }
        
        try:
            _configure_stripe()
            session = stripe.checkout.Session.retrieve(session_id)
            metadata = getattr(session, "metadata", {}) or {}
            payment_status = getattr(session, "payment_status", None)
            
            # Validate metadata matches
            if metadata.get("analysis_id") == analysis_id and payment_status == "paid":
                logger.debug(f"Stripe session {session_id} is paid, updating record")
                
                # Additional validation: verify amount and variant
                expected_variant = metadata.get("price_variant", "control")
                _validate_session_amount(session, expected_variant)
                
                record = _mark_paid_and_track(
                    analysis_id,
                    session_id=session.id,
                    amount_total=getattr(session, "amount_total", None),
                    customer_email=_extract_customer_email(session),
                    price_variant=expected_variant,
                )
        
        except stripe.error.StripeError as e:
            logger.warning(f"Failed to retrieve Stripe session {session_id}: {str(e)}")
            # Continue with local record, don't fail the request
        except Exception as e:
            logger.error(f"Unexpected error syncing payment status: {str(e)}")
    
    return {
        "analysis_id": analysis_id,
        "status": record.get("status", "unpaid"),
        "paid": record.get("status") == "paid",
        "checkout_session_id": record.get("checkout_session_id"),
        "paid_at": record.get("paid_at"),
        "customer_email": record.get("customer_email"),
        "price_variant": record.get("price_variant"),
    }


@router.get("/payments/history/{analysis_id}")
async def get_payment_history_endpoint(analysis_id: str):
    """Get complete payment history for an analysis (including refunds, failed attempts)."""
    logger.debug(f"Retrieving payment history for {analysis_id}")
    
    if analysis_id not in eob_analyses:
        logger.warning(f"Analysis not found: {analysis_id}")
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    try:
        history = get_payment_history(analysis_id)
        return {
            "analysis_id": analysis_id,
            "history": history,
        }
    except Exception as e:
        logger.error(f"Failed to retrieve payment history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment history")


@router.post("/payments/refund")
async def refund_payment(payload: RefundRequest):
    """Process a refund for a payment."""
    logger.info(f"Processing refund for analysis {payload.analysis_id}")
    
    if payload.analysis_id not in eob_analyses:
        logger.warning(f"Analysis not found: {payload.analysis_id}")
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    record = payment_status_by_analysis.get(payload.analysis_id, {})
    
    if record.get("status") != "paid":
        logger.warning(
            f"Cannot refund analysis {payload.analysis_id}: status is {record.get('status')}"
        )
        raise HTTPException(
            status_code=400,
            detail="Only paid payments can be refunded"
        )
    
    try:
        _configure_stripe()
        session_id = record.get("checkout_session_id")
        
        if not session_id:
            logger.error(f"No checkout session ID found for analysis {payload.analysis_id}")
            raise HTTPException(
                status_code=500,
                detail="Cannot process refund: session information missing"
            )
        
        # Retrieve the payment intent to refund
        session = stripe.checkout.Session.retrieve(session_id)
        payment_intent_id = getattr(session, "payment_intent", None)
        
        if not payment_intent_id:
            logger.error(f"No payment intent found for session {session_id}")
            raise HTTPException(
                status_code=500,
                detail="Cannot process refund: payment information missing"
            )
        
        # Create refund
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason="requested_by_customer" if not payload.reason else "other",
            metadata={
                "analysis_id": payload.analysis_id,
                "reason": payload.reason or "No reason provided",
            }
        )
        
        # Record refund in our system
        amount_total = record.get("amount_total") or EXPECTED_PRICE_CENTS.get(
            record.get("price_variant", "control")
        )
        
        record_refund(
            payload.analysis_id,
            amount_total or 0,
            payload.reason or "Customer-requested refund",
            refund.id
        )
        
        _log_payment_event(
            "payment_refunded",
            payload.analysis_id,
            amount_total=amount_total,
            price_variant=record.get("price_variant"),
        )
        
        logger.info(
            f"Refund processed: {refund.id} for analysis {payload.analysis_id}"
        )
        
        return {
            "refund_id": refund.id,
            "analysis_id": payload.analysis_id,
            "amount": amount_total,
            "status": refund.status,
        }
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error processing refund: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process refund")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing refund: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process refund")


@router.post("/payments/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    logger.debug("Received Stripe webhook")
    
    _configure_stripe()
    webhook_secret = _require_env("STRIPE_WEBHOOK_SECRET")
    
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    
    if not signature:
        logger.warning("Webhook received without signature")
        raise HTTPException(status_code=400, detail="Missing Stripe signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret
        )
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid webhook signature: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except ValueError as e:
        logger.warning(f"Invalid webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    
    event_id = event.get("id")
    
    # Check for duplicate processing (idempotency)
    if not validate_stripe_event_id(event_id):
        logger.warning(f"Invalid event ID format: {event_id}")
        return {"received": True}
    
    # Record webhook event for idempotency
    if not record_webhook_event(event_id):
        logger.debug(f"Duplicate webhook event received: {event_id}, skipping processing")
        return {"received": True}
    
    event_type = event.get("type")
    logger.info(f"Processing webhook event: {event_type} (ID: {event_id})")
    
    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(event)
        
        elif event_type == "charge.refunded":
            _handle_charge_refunded(event)
        
        elif event_type == "charge.dispute.created":
            _handle_dispute_created(event)
        
        elif event_type == "payment_intent.payment_failed":
            _handle_payment_failed(event)
        
        else:
            logger.debug(f"Unhandled webhook event type: {event_type}")
    
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {str(e)}")
        # Still return success to Stripe to prevent retries
        # The event is recorded so we won't process it again
    
    return {"received": True}


def _handle_checkout_completed(event: dict) -> None:
    """Handle checkout.session.completed event."""
    session = event["data"]["object"]
    metadata = session.get("metadata", {}) or {}
    analysis_id = (
        metadata.get("analysis_id") 
        or checkout_session_to_analysis.get(session.get("id"))
    )
    
    if not analysis_id:
        logger.warning(f"No analysis_id found in checkout session {session.get('id')}")
        return
    
    _mark_paid_and_track(
        analysis_id,
        session_id=session.get("id"),
        amount_total=session.get("amount_total"),
        customer_email=_extract_customer_email(session),
        price_variant=metadata.get("price_variant"),
    )


def _handle_charge_refunded(event: dict) -> None:
    """Handle charge.refunded event."""
    charge = event["data"]["object"]
    metadata = charge.get("metadata", {}) or {}
    analysis_id = metadata.get("analysis_id")
    
    if not analysis_id:
        logger.warning(f"No analysis_id found in refunded charge {charge.get('id')}")
        return
    
    refund_amount = charge.get("amount_refunded")
    record_refund(
        analysis_id,
        refund_amount or 0,
        "Charged refunded by Stripe",
        charge.get("id"),
    )
    
    logger.info(
        f"Refund processed from webhook: analysis={analysis_id}, "
        f"amount={format_amount_for_display(refund_amount or 0)}"
    )


def _handle_dispute_created(event: dict) -> None:
    """Handle charge.dispute.created event (chargeback)."""
    dispute = event["data"]["object"]
    charge_id = dispute.get("charge")
    
    try:
        _configure_stripe()
        charge = stripe.Charge.retrieve(charge_id)
        metadata = charge.get("metadata", {}) or {}
        analysis_id = metadata.get("analysis_id")
        
        if analysis_id:
            _log_payment_event(
                "payment_disputed",
                analysis_id,
                error=f"Dispute created: {dispute.get('reason')}",
            )
            logger.warning(
                f"Payment dispute created for analysis {analysis_id}: {dispute.get('reason')}"
            )
    except Exception as e:
        logger.error(f"Failed to handle dispute event: {str(e)}")


def _handle_payment_failed(event: dict) -> None:
    """Handle payment_intent.payment_failed event."""
    payment_intent = event["data"]["object"]
    metadata = payment_intent.get("metadata", {}) or {}
    analysis_id = metadata.get("analysis_id")
    last_error = payment_intent.get("last_payment_error", {}) or {}
    
    if not analysis_id:
        logger.warning(
            f"No analysis_id found in failed payment_intent {payment_intent.get('id')}"
        )
        return
    
    error_message = last_error.get("message", "Unknown error")
    error_code = last_error.get("code", "unknown")
    
    record_failed_payment_attempt(analysis_id, error_message, error_code)
    
    _log_payment_event(
        "payment_failed",
        analysis_id,
        error=f"{error_code}: {error_message}",
    )
    
    logger.warning(
        f"Payment failed for analysis {analysis_id}: {error_code} - {error_message}"
    )