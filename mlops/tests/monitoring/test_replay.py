"""Replay sender (ADR-0016). Blob storage and HTTP are replaced with in-memory fakes."""

from __future__ import annotations

import io
import urllib.error

import pytest

import bankml.monitoring.replay as replay


def test_next_batch_wraps_at_the_end_of_the_file():
    lines = ["a", "b", "c", "d", "e"]

    batch, next_position = replay.next_batch(lines, position=3, batch_size=4)

    assert batch == ["d", "e", "a", "b"]
    assert next_position == 2


def test_next_batch_never_sends_one_request_twice_in_a_run():
    batch, next_position = replay.next_batch(["a", "b"], position=1, batch_size=10)

    assert batch == ["b", "a"]
    assert next_position == 1


def test_next_batch_of_an_empty_file_is_empty():
    assert replay.next_batch([], position=7, batch_size=10) == ([], 0)


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_request_marks_the_request_as_replay(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["source"] = request.get_header("X-traffic-source")
        seen["auth"] = request.get_header("Authorization")
        return _Response(200)

    monkeypatch.setattr(replay.urllib.request, "urlopen", fake_urlopen)

    status = replay.post_request("https://api.example/", "/predict/credit", "{}", "k" * 32)

    assert status == 200
    assert seen == {
        "url": "https://api.example/predict/credit",
        "source": "replay",
        "auth": "Bearer " + "k" * 32,
    }


def test_post_request_retries_server_errors_but_not_client_errors(monkeypatch):
    monkeypatch.setattr(replay.time, "sleep", lambda seconds: None)
    calls = []

    def failing(code):
        def fake_urlopen(request, timeout):
            calls.append(code)
            raise urllib.error.HTTPError(request.full_url, code, "error", {}, io.BytesIO())

        return fake_urlopen

    monkeypatch.setattr(replay.urllib.request, "urlopen", failing(503))
    assert replay.post_request("https://api.example", "/predict/credit", "{}", "key") == 503
    assert len(calls) == 1 + replay._RETRIES

    calls.clear()
    monkeypatch.setattr(replay.urllib.request, "urlopen", failing(422))
    assert replay.post_request("https://api.example", "/predict/credit", "{}", "key") == 422
    assert len(calls) == 1


@pytest.fixture
def fake_store(monkeypatch):
    store = {"lines": [f'{{"applicant_id": {i}}}' for i in range(5)], "cursor": 3}
    monkeypatch.setattr(replay, "load_requests", lambda domain: store["lines"])
    monkeypatch.setattr(replay, "read_cursor", lambda domain: store["cursor"])
    monkeypatch.setattr(
        replay, "write_cursor", lambda domain, position: store.__setitem__("cursor", position)
    )
    return store


def test_run_replay_sends_a_batch_and_advances_the_cursor(monkeypatch, fake_store):
    sent = []
    monkeypatch.setattr(
        replay, "post_request", lambda url, endpoint, body, key: sent.append(body) or 200
    )

    result = replay.run_replay("credit", "https://api.example", "key", batch_size=3)

    assert sent == ['{"applicant_id": 3}', '{"applicant_id": 4}', '{"applicant_id": 0}']
    assert result["sent"] == 3
    assert result["failed"] == 0
    assert fake_store["cursor"] == 1


def test_run_replay_counts_failures_and_still_moves_on(monkeypatch, fake_store):
    statuses = iter([200, 500, 422])
    monkeypatch.setattr(replay, "post_request", lambda url, endpoint, body, key: next(statuses))

    result = replay.run_replay("credit", "https://api.example", "key", batch_size=3)

    assert result["sent"] == 1
    assert result["failed"] == 2
    assert result["statuses"] == {"200": 1, "422": 1, "500": 1}
    assert fake_store["cursor"] == 1
