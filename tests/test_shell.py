import shutil
import subprocess
import sys
import unittest

from support import BIN, REPO, Sandbox


class Wrapper(Sandbox):
    """The shell hook leaves the calling shell in the resumed session's directory."""

    def setUp(self):
        super().setUp()
        self.work = self.dir("code", "shop")
        self.session("11111111-1111-1111-1111-111111111111", "Checkout tax split", self.work,
                     "main", "rounding", "ok")
        self.stub("threadr", f'#!/bin/sh\nexec "{sys.executable}" "{BIN}" "$@"\n')

    def shell(self, name, script):
        exe = shutil.which(name)
        if not exe:
            self.skipTest(f"{name} not installed")
        return subprocess.run([exe, "-c", f'eval "$(threadr init {name})"; {script}'],
                              cwd=self.tmp, env=self.env, capture_output=True, text=True,
                              timeout=60)

    def check(self, name):
        done = self.shell(name, "threadr checkout; echo \"AFTER $(pwd)\"")
        self.assertHas(done.stdout, "CLAUDE --resume 11111111")
        self.assertHas(done.stdout, f"AFTER {self.work}")

        done = self.shell(name, "threadr -C checkout; echo \"AFTER $(pwd)\"")
        self.assertHas(done.stdout, f"AFTER {self.tmp}")

        done = self.shell(name, "threadr nothing-matches; echo \"RC $? AFTER $(pwd)\"")
        self.assertHas(done.stdout, f"RC 1 AFTER {self.tmp}")
        self.assertEqual(list(self.tmp.glob("threadr.*")), [])

    def test_zsh(self):
        self.check("zsh")

    def test_bash(self):
        self.check("bash")


class Install(Sandbox):
    def install(self, *args):
        env = {**self.env, "THREADR_BIN_DIR": str(self.home / ".local" / "bin"),
               "THREADR_RC": str(self.home / ".zshrc")}
        return subprocess.run(["bash", str(REPO / "install.sh"), *args], env=env,
                              capture_output=True, text=True)

    def test_dry_run_changes_nothing(self):
        out = self.install("--dry-run").stdout
        self.assertHas(out, "would append")
        self.assertFalse((self.home / ".local" / "bin" / "threadr").exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_install_is_idempotent_and_reversible(self):
        link = self.home / ".local" / "bin" / "threadr"
        link.parent.mkdir(parents=True)
        link.write_text("an old script")

        out = self.install().stdout
        self.assertHas(out, "BACKUP")
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), BIN.resolve())
        self.assertTrue((link.parent / "threadr.bak").is_file())
        rc = (self.home / ".zshrc").read_text()
        self.assertHas(rc, f'source "{REPO}/src/threadr/threadr.sh"')

        out = self.install().stdout
        self.assertHas(out, "already loads")
        self.assertEqual((self.home / ".zshrc").read_text().count("threadr.sh"), 1)

        self.install("--uninstall")
        self.assertFalse(link.exists())
        self.assertHasnt((self.home / ".zshrc").read_text(), "threadr")


if __name__ == "__main__":
    unittest.main()
