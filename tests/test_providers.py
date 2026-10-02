"""The provider contract: a second agent slots in without touching search or tree."""
from pathlib import Path

from support import Sandbox

from threadr import index, tree
from threadr.providers import Claude, Provider


class Notes(Provider):
    """A toy agent that stores one plain-text file per session."""

    name = "notes"
    binary = "notes"

    def __init__(self, root: Path):
        self.root = root

    def transcripts(self):
        return sorted(self.root.glob("*.txt"))

    def scan(self, path):
        text = path.read_text()
        return {"id": path.stem, "title": text.splitlines()[0], "cwd": "/notes", "branch": "",
                "prompts": [text], "replies": [], "fallback": "", "turns": 1,
                "first": "", "last": ""}

    def resume_argv(self, session_id, yolo=False):
        return ["notes", "open", session_id]


class Contract(Sandbox):
    def setUp(self):
        super().setUp()
        self.session("11111111-1111-1111-1111-111111111111", "Shared word kiwi",
                     self.dir("a"), "main", "kiwi in claude", "ok")
        root = self.dir("notes")
        (root / "n1.txt").write_text("Kiwi in notes\nmore text")
        self.providers = [Claude(), Notes(root)]

    def test_search_spans_providers(self):
        entries = index.search(index.load(self.providers), ["kiwi"], self.providers)
        self.assertEqual({e["provider"] for e in entries}, {"claude", "notes"})

    def test_same_id_in_two_providers_stays_two_rows(self):
        (self.dir("notes") / "11111111-1111-1111-1111-111111111111.txt").write_text("dup")
        ids = [e["id"] for e in index.load(self.providers)]
        self.assertEqual(ids.count("11111111-1111-1111-1111-111111111111"), 2)

    def test_tree_skips_providers_without_lineage(self):
        self.assertEqual(tree.collect([self.providers[1]]), [])

    def test_defaults_switch_features_off(self):
        notes = self.providers[1]
        self.assertIsNone(notes.fork_argv("n1", "x"))
        self.assertIsNone(notes.current_session())
        self.assertIsNone(notes.recover("n1"))
