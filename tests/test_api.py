"""HTTP client behavior — pagination against a stubbed server.

The regression here shipped: the server's ``current-item-index`` is the
journal HEAD on every page, not a continuation cursor. Treating it as one
made ``pull_items`` jump from page one straight past the tail of the
journal, silently dropping every commit in between — deletions and
completions synced by the apps never reached the CLI's cached state.
"""

from __future__ import annotations

from things_cli.api import Client, Session


class _PagedStub(Client):
    """Serves a journal in fixed-size pages the way the real server does:
    every page reports the same head index and total content size, and
    ``start-index`` is the only cursor."""

    def __init__(self, commits, page_size):
        super().__init__(Session(email="t@example.com", history_key="k"))
        self._commits = commits
        self._page_size = page_size
        self.requests = []

    def items_page(self, start_index):
        self.requests.append(start_index)
        items = self._commits[start_index : start_index + self._page_size]
        # 1 byte of "content" per commit keeps the size bookkeeping simple.
        return {
            "items": items,
            "current-item-index": len(self._commits),
            "start-total-content-size": start_index,
            "end-total-content-size": start_index + len(items),
            "latest-total-content-size": len(self._commits),
        }


def _journal(n):
    return [{f"uuid{i}": {"t": 0, "e": "Task6", "p": {"tt": str(i)}}} for i in range(n)]


def test_pull_items_fetches_every_page():
    """A journal larger than one page must come back whole — the missing
    middle is exactly where the apps' deletes and completions live."""
    stub = _PagedStub(_journal(1000), page_size=300)
    commits, head = stub.pull_items(0)
    assert len(commits) == 1000
    assert head == 1000
    assert stub.requests == [0, 300, 600, 900]


def test_pull_items_does_not_use_head_index_as_cursor():
    """The shipped bug: after page one the next request jumped to the head
    index, returned nothing, and pull terminated with only page one."""
    stub = _PagedStub(_journal(500), page_size=100)
    commits, _ = stub.pull_items(0)
    assert stub.requests == [0, 100, 200, 300, 400]
    assert len(commits) == 500


def test_pull_items_incremental_from_cached_head():
    stub = _PagedStub(_journal(120), page_size=50)
    commits, head = stub.pull_items(100)
    assert len(commits) == 20
    assert head == 120


def test_pull_items_empty_history():
    stub = _PagedStub([], page_size=50)
    commits, head = stub.pull_items(0)
    assert commits == []
    assert head == 0
