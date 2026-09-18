"""
Basic security utilities.
Placeholder for future authentication and authorization.
"""

import secrets
from datetime import datetime, timezone


def generate_inspection_token() -> str:
    """Generate a unique token for an inspection session."""
    return secrets.token_urlsafe(16)


def get_current_timestamp() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)
