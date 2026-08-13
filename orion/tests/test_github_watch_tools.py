from tools.github_watch_tools import RecentGithubCommitsTool


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


def _commit(message, sha="abcdef1234567890", author="Nathan"):
    return {"sha": sha, "commit": {"message": message, "author": {"name": author}}}


def test_lists_recent_commits(monkeypatch):
    monkeypatch.setattr(
        "tools.github_watch_tools.client.get",
        lambda *a, **kw: _FakeResponse([_commit("Fix the bug")]),
    )
    result = RecentGithubCommitsTool().run(owner="acme", repo="widgets")
    assert "Fix the bug" in result
    assert "Nathan" in result


def test_no_commits(monkeypatch):
    monkeypatch.setattr("tools.github_watch_tools.client.get", lambda *a, **kw: _FakeResponse([]))
    result = RecentGithubCommitsTool().run(owner="acme", repo="widgets")
    assert "No commits found" in result


def test_empty_commit_message_does_not_crash_the_whole_listing(monkeypatch):
    """Regression test: git commit --allow-empty-message (or certain merge/
    revert bots) produces a commit whose message is ''. ''.splitlines()
    is [] — indexing [0] on that used to raise IndexError and abort the
    *entire* commit listing over one commit, instead of just showing that
    one with no message and continuing."""
    monkeypatch.setattr(
        "tools.github_watch_tools.client.get",
        lambda *a, **kw: _FakeResponse([_commit(""), _commit("Normal commit")]),
    )

    result = RecentGithubCommitsTool().run(owner="acme", repo="widgets")

    assert "(empty commit message)" in result
    assert "Normal commit" in result
