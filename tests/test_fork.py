import os
import shutil
import subprocess
import unittest

from support import Sandbox

from threadr.mux.herdr import APP_BINARY

CREATED = '{"result":{"workspace":{"workspace_id":"ws1"},"root_pane":{"pane_id":"p1"}}}'
HERDR = """#!/bin/sh
echo "HERDR $*" >> "{log}"
case "$1 $2" in
  "workspace create") echo '{created}' ;;
esac
"""

TMUX = """#!/bin/sh
echo "TMUX $*" >> "{log}"
case "$1" in new-window) echo "main:3" ;; esac
"""


class Fork(Sandbox):
    def setUp(self):
        super().setUp()
        self.work = self.dir("work")
        self.log = self.tmp / "argv"
        self.log.write_text("")
        self.stub("herdr", HERDR.format(log=self.log, created=CREATED))
        self.stub("tmux", TMUX.format(log=self.log))
        self.env["CLAUDE_CODE_SESSION_ID"] = "sid-123"

    def fork(self, *args, **env):
        result = self.run_threadr("fork", *args, cwd=self.work, env=env)
        return result.out, self.log.read_text()

    # --- preconditions -----------------------------------------------------------
    def test_needs_a_session(self):
        del self.env["CLAUDE_CODE_SESSION_ID"]
        self.assertHas(self.fork("x")[0], "not inside a supported agent session")

    def test_needs_the_agent(self):
        (self.bin / "claude").unlink()
        self.assertHas(self.fork("x")[0], "claude not found on PATH")

    def test_needs_a_mux(self):
        (self.bin / "herdr").unlink()
        (self.bin / "tmux").unlink()
        if shutil.which("tmux", path="/usr/bin:/bin") or os.path.exists(APP_BINARY):
            self.skipTest("a multiplexer is installed system-wide")
        self.assertHas(self.fork("x", THREADR_MUX="")[0], "install herdr or tmux")

    def test_unknown_mux(self):
        self.assertHas(self.fork("x", THREADR_MUX="screen")[0], "unknown THREADR_MUX: screen")

    # --- tmux --------------------------------------------------------------------
    def test_tmux_window_inside_tmux(self):
        out, argv = self.fork("my-label", TMUX="/tmp/sock", THREADR_MUX="tmux")
        self.assertHas(argv, "TMUX new-window")
        self.assertHas(argv, f"-c {self.work}")
        self.assertHas(argv, "-n my-label")
        self.assertHas(argv, "claude --resume sid-123 --fork-session --name my-label")
        self.assertHas(out, "tmux window main:3")
        self.assertHas(out, "tmux kill-window -t main:3")
        self.assertHasnt(argv, "dangerously-skip-permissions")

    def test_tmux_session_outside_tmux(self):
        out, argv = self.fork("my-label", THREADR_MUX="tmux")
        self.assertHas(argv, "TMUX new-session -d -s my-label")
        self.assertHas(out, "tmux attach -t my-label")

    def test_tmux_names_are_sanitised(self):
        _, argv = self.fork("a.b:c", THREADR_MUX="tmux")
        self.assertHas(argv, "-s a-b-c")
        self.assertHas(argv, "--name a.b:c")

    def test_default_label(self):
        _, argv = self.fork(TMUX="/tmp/sock", THREADR_MUX="tmux")
        self.assertHas(argv, "--name fork-")

    def test_yolo(self):
        _, argv = self.fork("y", THREADR_MUX="tmux", THREADR_YOLO="1")
        self.assertHas(argv, "--dangerously-skip-permissions")

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_dirty_tree_is_named(self):
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", "."], cwd=self.work, check=True)
        (self.work / "tracked.txt").write_text("hello")
        subprocess.run(git + ["add", "."], cwd=self.work, check=True)
        subprocess.run(git + ["commit", "-qm", "init"], cwd=self.work, check=True)
        (self.work / "tracked.txt").write_text("changed")
        out, _ = self.fork("dirty", THREADR_MUX="tmux", TMUX="/tmp/sock")
        self.assertHas(out, "working tree is dirty")
        self.assertHas(out, "tracked.txt")
        self.assertHas(out, "tmux window")

    # --- herdr -------------------------------------------------------------------
    def test_herdr_workspace(self):
        out, argv = self.fork("herdr-label", HERDR_ENV="1")
        self.assertHas(argv, f"workspace create --cwd {self.work} --label herdr-label --no-focus")
        self.assertHas(argv, "pane run p1 claude --resume sid-123 --fork-session "
                             "--name herdr-label")
        self.assertHas(argv, "workspace focus ws1")
        self.assertHas(out, "herdr workspace ws1  pane p1")
        self.assertHasnt(argv, "dangerously-skip-permissions")

    def test_detection_order(self):
        self.assertHas(self.fork("a", HERDR_ENV="1", TMUX="/tmp/sock")[0], "herdr workspace")
        self.assertHas(self.fork("b", TMUX="/tmp/sock")[0], "tmux window")
        self.assertHas(self.fork("c")[0], "herdr workspace")

    def test_herdr_garbage_is_reported(self):
        self.stub("herdr", "#!/bin/sh\necho not-json\n")
        self.assertHas(self.fork("x", HERDR_ENV="1")[0], "could not read workspace and pane ids")


@unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
class RealTmux(Sandbox):
    """The stubs prove the arguments; this proves tmux accepts them.

    TMUX_TMPDIR gives this test its own tmux server, so it can never see or
    kill the sessions of whoever runs the suite.
    """

    def test_real_tmux_accepts_the_invocation(self):
        tmux = shutil.which("tmux")
        # Keep the fork alive long enough to be listed; a real agent would be.
        self.stub("claude", "#!/bin/sh\nsleep 30\n")
        sockets = self.tmp / "tmux"
        sockets.mkdir()
        self.env.update(TMUX_TMPDIR=str(sockets), CLAUDE_CODE_SESSION_ID="sid-123",
                        THREADR_MUX="tmux",
                        PATH=f"{self.bin}:{os.path.dirname(tmux)}:/usr/bin:/bin")
        self.addCleanup(subprocess.run, [tmux, "kill-server"], env=self.env, capture_output=True)
        result = self.run_threadr("fork", "smoke-test", cwd=self.tmp)
        self.assertHas(result.out, "detached tmux session 'smoke-test'")
        listed = subprocess.run([tmux, "list-sessions", "-F", "#{session_name}"], env=self.env,
                                capture_output=True, text=True).stdout
        self.assertHas(listed, "smoke-test")
