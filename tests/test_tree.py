import json

from support import Sandbox


def emit(uuid, stamp, kind, cwd, text="ok"):
    rec = {"type": kind, "uuid": uuid, "timestamp": stamp, "cwd": str(cwd), "gitBranch": "main"}
    rec["message"] = {"content": text if kind == "user" else [{"type": "text", "text": text}]}
    return json.dumps(rec, separators=(",", ":")) + "\n"


class Tree(Sandbox):
    """A parent that kept going, and a fork taken off its first 8 messages.

    The parent's own messages start at 10:07 and the fork's at 14:00, which is
    the only thing that says which of the two is the parent.
    """

    def setUp(self):
        super().setUp()
        self.work = self.dir("code", "shop")
        shared = "".join(
            emit(f"aaaaaaaa-0000-0000-0000-0000000000{i:02d}", f"2026-09-01T10:0{i - 1}:00.000Z",
                 "user" if i % 2 else "assistant", self.work, f"shared turn {i}")
            for i in range(1, 9))
        self.write("aaaaaaaa-1111-1111-1111-111111111111", "parent-line", shared
                   + emit("aaaaaaaa-0000-0000-0000-000000000009", "2026-09-01T10:07:00.000Z",
                          "user", self.work, "parent keeps going")
                   + emit("aaaaaaaa-0000-0000-0000-000000000010", "2026-09-01T10:07:30.000Z",
                          "assistant", self.work))
        self.write("bbbbbbbb-2222-2222-2222-222222222222", "the-fork", shared
                   + emit("bbbbbbbb-0000-0000-0000-000000000001", "2026-09-01T14:00:00.000Z",
                          "user", self.work, "the fork goes its own way")
                   + emit("bbbbbbbb-0000-0000-0000-000000000002", "2026-09-01T14:00:30.000Z",
                          "assistant", self.work))
        self.write("cccccccc-3333-3333-3333-333333333333", "a-loner",
                   emit("cccccccc-0000-0000-0000-000000000001", "2026-09-02T09:00:00.000Z",
                        "user", self.work, "all alone")
                   + emit("cccccccc-0000-0000-0000-000000000002", "2026-09-02T09:00:30.000Z",
                          "assistant", self.work))

    def write(self, sid, title, body):
        path = self.projects / f"{sid}.jsonl"
        path.write_text(json.dumps({"type": "custom-title", "customTitle": title}) + "\n" + body)

    def test_ascii(self):
        out = self.run_threadr("tree", "--no-color", "--cwd", str(self.work)).out
        self.assertHas(out, "2 sessions, 1 fork")
        self.assertHas(out, "parent-line  [main line]")
        self.assertHas(out, "the-fork  [fork]")
        self.assertHas(out, "inherited 8 msgs")
        self.assertHas(out, "forked 01 Sep")
        self.assertHas(out, str(self.work))
        self.assertHas(out, "the fork goes its own way")

    def test_unforked_sessions_only_with_all(self):
        self.assertHasnt(self.run_threadr("tree", "--no-color").out, "a-loner")
        self.assertHas(self.run_threadr("tree", "--no-color", "--all").out, "a-loner")

    def test_json(self):
        data = json.loads(self.run_threadr("tree", "--json").stdout)
        root = data[0]["tree"]
        self.assertEqual(root["title"], "parent-line")
        self.assertFalse(root["isFork"])
        fork = root["children"][0]
        self.assertEqual(fork["title"], "the-fork")
        self.assertTrue(fork["isFork"])
        self.assertEqual(fork["inherited"], 8)
        self.assertEqual(fork["resume"], "claude --resume bbbbbbbb-2222-2222-2222-222222222222")

    def test_mermaid(self):
        out = self.run_threadr("tree", "--mermaid").out
        self.assertHas(out, "flowchart LR")
        self.assertHas(out, "+8 msgs")

    def test_html(self):
        target = self.tmp / "map.html"
        self.run_threadr("tree", "--html", str(target))
        page = target.read_text()
        self.assertHasnt(page, "__DATA__")
        self.assertHas(page, "parent-line")
        self.assertHas(page, "claude --resume")

    def test_html_cannot_be_broken_out_of(self):
        self.write("dddddddd-4444-4444-4444-444444444444", "</script><b>x",
                   emit("aaaaaaaa-0000-0000-0000-000000000001", "2026-09-01T10:00:00.000Z",
                        "user", self.work, "shared turn 1")
                   + emit("aaaaaaaa-0000-0000-0000-000000000002", "2026-09-01T10:01:00.000Z",
                          "assistant", self.work)
                   + emit("dddddddd-0000-0000-0000-000000000001", "2026-09-03T10:00:00.000Z",
                          "user", self.work, "late"))
        target = self.tmp / "map.html"
        self.run_threadr("tree", "--html", str(target))
        self.assertEqual(target.read_text().count("</script>"), 1)

    def test_nothing_forked(self):
        for path in self.projects.glob("[ab]*.jsonl"):
            path.unlink()
        result = self.run_threadr("tree")
        self.assertEqual(result.returncode, 1)
        self.assertHas(result.out, "No forked sessions")
