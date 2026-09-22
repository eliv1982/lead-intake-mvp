"""Real subprocess regression for the temp-directory cleanup issue.

`tests/__init__.py`'s `_cleanup_test_dir` closes and detaches the event
logger's `FileHandler` before calling `rmtree` on the directory holding the
log file - on Windows, `rmtree` raises `PermissionError` on a file that is
still open. A synthetic logger standing in for the real one only proves
that pattern works in isolation; it does not prove the *actual* test
bootstrap (`tests/__init__.py`) and the *actual* SQLite connection
lifecycle (`app.database`, `app.main.create_lead`) leave nothing open by
the time `atexit` runs `rmtree` on the process's real `TEST_DIR`.

So this module runs the real `EventLoggingTests` - the smallest real test
that reproduces the post-commit `event_logger.info()` exception path, which
is what originally exposed a leaked SQLite connection keeping
`test_leads.db` open - in a child Python process, and inspects the OS temp
directory before and after.

This has to be a *subprocess* check, not just "the child exited 0": Python
ignores exceptions raised inside `atexit` callbacks for process exit-code
purposes, so a child whose cleanup silently failed can still exit 0. This
test does not trust the child's exit code alone - it independently lists
`lead_intake_mvp_tests_*` directories in the OS temp directory before and
after the child runs, and fails if the child leaves a new one behind. The
five directories documented as pre-existing from prior runs are left alone;
only directories that appear during this child invocation count.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT = Path(tempfile.gettempdir())

CHILD_TIMEOUT_SECONDS = 60


def _lead_intake_test_dirs() -> set:
    if not TEMP_ROOT.exists():
        return set()
    return {
        entry.name
        for entry in TEMP_ROOT.iterdir()
        if entry.is_dir() and entry.name.startswith("lead_intake_mvp_tests_")
    }


class CleanupSubprocessRegressionTests(unittest.TestCase):
    """Runs the real `EventLoggingTests` in a child process and proves the
    real `tests/__init__.py` bootstrap leaves no temp directory behind,
    even on the post-commit logging-exception path."""

    def test_event_logging_tests_child_process_leaves_no_temp_dir(self) -> None:
        before = _lead_intake_test_dirs()

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "tests.test_api.EventLoggingTests",
                    "-v",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=CHILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            # subprocess.run already killed and reaped the child before
            # re-raising this, so nothing is left running.
            self.fail(
                "Child EventLoggingTests process did not finish within "
                f"{CHILD_TIMEOUT_SECONDS}s.\n"
                f"--- partial child stdout ---\n{error.stdout}\n"
                f"--- partial child stderr ---\n{error.stderr}"
            )

        after = _lead_intake_test_dirs()
        new_dirs = after - before

        details = (
            f"child exit code: {result.returncode}\n"
            f"--- child stdout ---\n{result.stdout}\n"
            f"--- child stderr ---\n{result.stderr}\n"
            f"new lead_intake_mvp_tests_* dirs left behind: {sorted(new_dirs)}"
        )

        self.assertEqual(
            result.returncode, 0, f"Child test process did not exit 0.\n{details}"
        )
        self.assertEqual(
            new_dirs,
            set(),
            "Child process left a lead_intake_mvp_tests_* temp directory "
            f"behind (leaked resource kept it locked).\n{details}",
        )


if __name__ == "__main__":
    unittest.main()
