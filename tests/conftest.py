"""Pytest configuration and fixtures."""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables for testing
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_123456")
os.environ.setdefault("STRIPE_PRICE_ID", "price_test123")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test123")
os.environ.setdefault("DEBUG", "false")
