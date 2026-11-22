"""Panel admin roles ported from the café pilot."""

from uuid import uuid4

import pytest

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.panel_access import clean_job_title, roles_assignable_by
from factory_os.domain.store import MemoryCommerceStore


def test_owner_cannot_assign_owner_or_admin() -> None:
    assert roles_assignable_by("owner") == frozenset({"supervisor", "staff"})
    assert roles_assignable_by("admin") == frozenset({"owner", "supervisor", "staff"})


def test_job_title_only_for_staff() -> None:
    assert clean_job_title("staff", "cajero") == "cajero"
    assert clean_job_title("owner", "cajero") == ""
    with pytest.raises(ValueError):
        clean_job_title("staff", "x" * 41)


def test_memory_store_keeps_job_title_and_resets_secret() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    user = store.add_panel_user(
        PILOT_TENANT_ID,
        "Ana",
        "ana@cafe.test",
        "staff",
        "salt",
        "hash",
        job_title="cajero",
    )
    assert user.job_title == "cajero"
    updated = store.set_panel_user_secret(PILOT_TENANT_ID, user.id, "salt2", "hash2")
    assert updated.secret_hash == "hash2"
    assert updated.job_title == "cajero"
    with pytest.raises(KeyError):
        store.set_panel_user_secret(PILOT_TENANT_ID, uuid4(), "s", "h")
