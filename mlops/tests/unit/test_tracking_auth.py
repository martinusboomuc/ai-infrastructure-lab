from bankml.tracking_auth import CloudflareAccessRequestHeaderProvider


def test_out_of_context_when_no_credentials_are_set(monkeypatch):
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    assert CloudflareAccessRequestHeaderProvider().in_context() is False


def test_out_of_context_when_only_one_credential_is_set(monkeypatch):
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id-only")
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    assert CloudflareAccessRequestHeaderProvider().in_context() is False


def test_in_context_and_attaches_both_headers_when_both_credentials_are_set(monkeypatch):
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "some-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "some-secret")
    provider = CloudflareAccessRequestHeaderProvider()
    assert provider.in_context() is True
    assert provider.request_headers() == {
        "CF-Access-Client-Id": "some-id",
        "CF-Access-Client-Secret": "some-secret",
    }
