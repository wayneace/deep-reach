import unittest

from deep_reach.backends.github import _issue_item, _repo_item, _repo_slug
from deep_reach.backends.v2ex import (
    _node_name,
    _reply_item,
    _topic_id,
    _topic_item,
)
from deep_reach.channels import load_registry
from deep_reach.runtime.result import BAD_INPUT, ReachError


class GitHubParseTest(unittest.TestCase):
    def test_repo_slug_from_url_and_slug(self):
        self.assertEqual(
            _repo_slug("https://github.com/Panniantong/Agent-Reach"),
            "Panniantong/Agent-Reach",
        )
        self.assertEqual(_repo_slug("Panniantong/Agent-Reach"), "Panniantong/Agent-Reach")

    def test_repo_slug_rejects_garbage(self):
        with self.assertRaises(ReachError) as ctx:
            _repo_slug("not a repo")
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_repo_item_metrics(self):
        row = {
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
            "owner": {"login": "owner"},
            "description": "a repo",
            "pushed_at": "2026-11-01T00:00:00Z",
            "stargazers_count": 10,
            "forks_count": 2,
            "open_issues_count": 3,
            "watchers_count": 10,
        }
        item = _repo_item(row)
        self.assertEqual(item["source"], "github")
        self.assertEqual(item["url"], "https://github.com/owner/repo")
        self.assertEqual(item["metrics"]["stars"], 10)
        self.assertEqual(item["backend"], "github-api")

    def test_issue_item_parent_is_repo(self):
        row = {
            "title": "bug",
            "html_url": "https://github.com/owner/repo/issues/1",
            "user": {"login": "alice"},
            "created_at": "2026-10-01T00:00:00Z",
            "body": "text",
            "comments": 4,
            "reactions": {"total_count": 7},
        }
        item = _issue_item(row, "owner/repo")
        self.assertEqual(item["parent_id"], "owner/repo")
        self.assertEqual(item["metrics"], {"comments": 4, "reactions": 7})


class V2EXParseTest(unittest.TestCase):
    def test_topic_id_from_url_and_number(self):
        self.assertEqual(_topic_id("https://www.v2ex.com/t/123456"), 123456)
        self.assertEqual(_topic_id("123456"), 123456)
        with self.assertRaises(ReachError):
            _topic_id("not-a-topic")

    def test_node_name_from_url_and_name(self):
        self.assertEqual(_node_name("https://www.v2ex.com/go/create"), "create")
        self.assertEqual(_node_name("create"), "create")

    def test_topic_item(self):
        row = {
            "id": 123,
            "title": "topic",
            "url": "https://www.v2ex.com/t/123",
            "content": "hello",
            "replies": 5,
            "member": {"username": "alice"},
            "node": {"name": "create"},
            "created": 1700000000,
        }
        item = _topic_item(row)
        self.assertEqual(item["source"], "v2ex")
        self.assertEqual(item["author"], "alice")
        self.assertEqual(item["metrics"]["replies"], 5)
        self.assertEqual(item["published_at"], "2023-11-14T22:13:20Z")

    def test_reply_item(self):
        row = {
            "content": "reply",
            "created": 1700000000,
            "thanks": 2,
            "member": {"username": "bob"},
        }
        item = _reply_item(row, 123)
        self.assertEqual(item["parent_id"], "123")
        self.assertEqual(item["author"], "bob")
        self.assertEqual(item["metrics"]["thanks"], 2)


class ChannelRegistrationTest(unittest.TestCase):
    def test_github_and_v2ex_are_visible_p0(self):
        registry = load_registry()
        for name in ("github", "v2ex"):
            self.assertIn(name, registry.visible)
            channel = registry.visible[name]
            self.assertEqual(channel.level, "default")
            self.assertIn("p0", channel.tiers)
            self.assertTrue(channel.actions)


if __name__ == "__main__":
    unittest.main()
