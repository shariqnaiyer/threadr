from pathlib import Path

from support import Sandbox

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
GONE = "33333333-3333-3333-3333-333333333333"


class Find(Sandbox):
    def setUp(self):
        super().setUp()
        self.work = self.dir("code", "shop")
        self.other = self.dir("code", "other")
        self.session(A, "Checkout tax split", self.work, "feature/tax-split",
                     "why is the regional rounding wrong",
                     "Because the rate table rounds per line before the split.")
        self.session(B, "Billing ledger refactor", self.other, "refactor/ledger",
                     "convert the billing ledger to react", "Start with the charges grid.")
        self.history(GONE, "the deleted conversation about kestrels", self.home / "code" / "gone")

    # --- listing and search ------------------------------------------------------
    def test_lists_everything(self):
        out = self.run_threadr("--tsv").out
        self.assertHas(out, "Checkout tax split")
        self.assertHas(out, "Billing ledger refactor")
        self.assertHas(out, "gone")
        self.assertHasnt(out, "ignore me")

    def test_tsv_columns(self):
        row = self.run_threadr("--tsv", "checkout").stdout.splitlines()[0].split("\t")
        self.assertEqual(row[0], A)
        self.assertEqual(row[1], "claude")
        self.assertEqual(row[2], str(self.work))
        self.assertEqual(row[3], "feature/tax-split")
        self.assertEqual(row[7], "live")

    def test_searches_every_field(self):
        self.assertHas(self.run_threadr("--tsv", "checkout").out, A)
        self.assertHasnt(self.run_threadr("--tsv", "checkout").out, B)
        self.assertHas(self.run_threadr("--tsv", "rounds", "line").out, A)
        self.assertHas(self.run_threadr("--tsv", "refactor", "ledger").out, B)

    def test_deleted_sessions(self):
        out = self.run_threadr("--tsv", "kestrels").out
        self.assertHas(out, GONE)
        self.assertHas(out, "gone")
        self.assertHasnt(self.run_threadr("--tsv", "--live-only", "kestrels").out, GONE)

    def test_cwd_filter(self):
        out = self.run_threadr("--tsv", "--cwd", str(self.other)).out
        self.assertHas(out, B)
        self.assertHasnt(out, A)
        backslashed = str(self.other).replace("/", "\\")
        self.assertHas(self.run_threadr("--tsv", "--cwd", backslashed).out, B)

    def test_deep_scan_finds_what_the_digest_dropped(self):
        filler = "x" * 790
        long_reply = " ".join([filler] * 20) + " zanzibar"
        self.session("44444444-4444-4444-4444-444444444444", "Long one", self.work, "main",
                     "start", long_reply)
        result = self.run_threadr("--tsv", "zanzibar")
        self.assertHas(result.stderr, "scanning full transcripts")
        self.assertHas(result.stdout, "44444444")

    def test_partial_matches_are_labelled(self):
        result = self.run_threadr("--tsv", "checkout", "nonexistentword")
        self.assertHas(result.stderr, "best partial matches")
        self.assertHas(result.stdout, A)

    def test_miss(self):
        result = self.run_threadr("definitely-not-in-any-session")
        self.assertEqual(result.returncode, 1)
        self.assertHas(result.out, "No session matches")

    def test_limit_and_cache(self):
        self.assertEqual(len(self.run_threadr("--tsv", "-n", "1").stdout.splitlines()), 1)
        self.assertTrue((self.home / ".cache" / "threadr" / "index.json").is_file())
        self.assertFalse((self.home / ".claude" / ".cache").exists())

    def test_list_table(self):
        out = self.run_threadr("-l", "ledger").out
        self.assertHas(out, "TITLE")
        self.assertHas(out, "Billing ledger refactor")
        self.assertHasnt(out, "CLAUDE")

    def test_show_and_recover(self):
        out = self.run_threadr("show", A).out
        self.assertHas(out, "Checkout tax split")
        self.assertHas(out, "feature/tax-split")
        self.assertHas(out, "regional rounding")
        self.assertHas(self.run_threadr("show", "claude:" + A).out, "Checkout tax split")
        self.assertHas(self.run_threadr("recover", GONE).out, "deleted conversation about kestrels")

    def test_claude_config_dir_is_honoured(self):
        alt = self.tmp / "alt-claude"
        self.session("55555555-5555-5555-5555-555555555555", "Elsewhere", self.work, "main",
                     "hello", "hi", folder=alt / "projects" / "-x")
        out = self.run_threadr("--tsv", env={"CLAUDE_CONFIG_DIR": str(alt)}).out
        self.assertHas(out, "Elsewhere")
        self.assertHasnt(out, "Checkout tax split")

    # --- resuming ----------------------------------------------------------------
    def test_single_hit_resumes_in_its_directory(self):
        cdfile = self.tmp / "cd"
        out = self.run_threadr("checkout", env={"THREADR_CD_FILE": str(cdfile)}).out
        self.assertHas(out, "Resuming Checkout tax split")
        self.assertHas(out, f"CLAUDE --resume {A}")
        self.assertHas(out, f"PWD {self.work}")
        self.assertEqual(cdfile.read_text(), str(self.work))
        self.assertHasnt(out, "dangerously-skip-permissions")

    def test_herdr_alone_does_not_skip_permissions(self):
        out = self.run_threadr("checkout", env={"HERDR_ENV": "1"}).out
        self.assertHasnt(out, "dangerously-skip-permissions")

    def test_yolo_is_opt_in(self):
        out = self.run_threadr("checkout", env={"THREADR_YOLO": "1"}).out
        self.assertHas(out, f"--resume {A} --dangerously-skip-permissions")

    def test_no_cd_stays_put(self):
        cdfile = self.tmp / "cd"
        cdfile.write_text("")
        out = self.run_threadr("-C", "checkout", cwd=self.tmp,
                               env={"THREADR_CD_FILE": str(cdfile)}).out
        self.assertHas(out, f"PWD {self.tmp}")
        self.assertEqual(cdfile.read_text(), "")

    def test_missing_directory_resumes_in_place(self):
        self.session("66666666-6666-6666-6666-666666666666", "Orphaned dir",
                     self.home / "nowhere", "main", "lonely", "ok")
        out = self.run_threadr("orphaned").out
        self.assertHas(out, "Directory is gone")
        self.assertHas(out, "CLAUDE --resume 66666666")

    def test_gone_session_recovers_instead(self):
        result = self.run_threadr("kestrels")
        self.assertEqual(result.returncode, 1)
        self.assertHas(result.out, "cannot be resumed")
        self.assertHas(result.out, "deleted conversation about kestrels")
        self.assertHasnt(result.out, "CLAUDE --resume")

    def test_missing_agent_binary(self):
        (self.bin / "claude").unlink()
        self.assertHas(self.run_threadr("checkout").out, "claude not found on PATH")

    # --- pickers -----------------------------------------------------------------
    def test_numbered_menu(self):
        out = self.run_threadr(stdin="2\n").out
        self.assertHas(out, "  2)")
        self.assertHas(out, "CLAUDE --resume")
        self.assertHasnt(self.run_threadr(stdin="\n").out, "CLAUDE --resume")
        self.assertHas(self.run_threadr(stdin="9\n").out, "not a listed number: 9")
        self.assertHas(self.run_threadr(stdin="abc\n").out, "not a listed number: abc")

    def test_fzf_picker(self):
        argv = self.tmp / "fzf-argv"
        self.stub("fzf", f'#!/bin/sh\necho "$@" > "{argv}"\nsed -n 2p\n')
        out = self.run_threadr().out
        self.assertHas(out, "CLAUDE --resume")
        args = Path(argv).read_text()
        self.assertHas(args, "--with-nth=2,3,4,5,6")
        self.assertHas(args, "threadr show {1}")

    def test_fzf_escape_cancels(self):
        self.stub("fzf", "#!/bin/sh\nexit 130\n")
        result = self.run_threadr()
        self.assertEqual(result.returncode, 0)
        self.assertHasnt(result.out, "CLAUDE --resume")
