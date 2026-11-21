from agentos_sdk.client import AgentOS


def test_sdk_builds_auth_headers() -> None:
    client = AgentOS(
        base_url="http://example.test",
        api_key="aos_test",
        organization_id="11111111-1111-1111-1111-111111111111",
    )
    headers = client._headers(idempotency_key="abc")
    assert headers["Authorization"] == "Bearer aos_test"
    assert headers["X-Organization-Id"] == "11111111-1111-1111-1111-111111111111"
    assert headers["Idempotency-Key"] == "abc"
    client.close()
