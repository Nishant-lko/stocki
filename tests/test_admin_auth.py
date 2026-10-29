from warehouse_slotting.admin_auth import session_fingerprint, verify_admin


def test_admin_requires_configured_password_and_exact_credentials():
    assert not verify_admin("nishant", "anything", "")
    assert not verify_admin("nishant", "", "secret")
    assert not verify_admin("user", "secret", "secret")
    assert not verify_admin("admin", "secret", "secret")
    assert not verify_admin("nishant_100", "secret", "secret")
    assert not verify_admin("nishant", "wrong", "secret")
    assert verify_admin("nishant", "secret", "secret")


def test_password_rotation_invalidates_session_fingerprint():
    assert session_fingerprint("old") != session_fingerprint("new")
