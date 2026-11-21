from datetime import UTC, datetime, timedelta

import pytest
from agentos.identity.oauth import TokenError, issue_access_token, verify_access_token


def test_expired_token_is_rejected() -> None:
    token = issue_access_token(
        organization_id="11111111-1111-1111-1111-111111111111",
        application_id="22222222-2222-2222-2222-222222222222",
        credential_id="33333333-3333-3333-3333-333333333333",
        scopes=["orgs:read"],
        signing_key="test-signing-key-32bytes-minimum!",
        ttl_seconds=1,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(TokenError):
        verify_access_token(token, signing_key="test-signing-key-32bytes-minimum!")
