"""Minimal single-admin credential checks for the local dashboard."""

import hashlib
import hmac

ADMIN_USERNAME = "nishant"


def verify_admin(username: str, password: str, configured_password: str) -> bool:
    """Compare credentials without accepting an unset or blank password."""
    if not configured_password or not password:
        return False
    return hmac.compare_digest(username.strip().encode(), ADMIN_USERNAME.encode()) and hmac.compare_digest(
        password.encode(), configured_password.encode()
    )


def session_fingerprint(configured_password: str) -> str:
    """Invalidate existing sessions if the configured password changes."""
    return hashlib.sha256(("slotwise-admin-v1:" + ADMIN_USERNAME + ":" + configured_password).encode()).hexdigest()
