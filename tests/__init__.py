"""Test package bootstrap.

This redirects the application's SQLite database and event log to a
temporary directory *before* ``app.main`` (and therefore ``app.database``
and ``app.logger``) is imported anywhere in the test process. That way,
running the suite never reads or writes the repository's real
``data/leads.db`` or ``logs/events.log`` files.

This only works because ``tests/__init__.py`` is guaranteed to run before
any ``tests.*`` submodule is imported (standard Python package import
order), and because it is the very first thing in the process to import
``app.database`` / ``app.logger`` - before ``app.main`` ever creates its
module-level event logger singleton.

IMPORTANT: run the suite as a package (e.g. ``python -m unittest discover``
from the repository root, which is also what ``tests/README`` and the
project README document) so this module actually runs first. Running
``python -m unittest discover -s tests`` (i.e. treating ``tests`` itself as
the top-level dir) skips package initialization and defeats this
safeguard - the guard below turns that misuse into a loud failure instead
of silently writing to the repository's real database/log files.
"""

import atexit
import logging
import shutil
import sys
import tempfile
from pathlib import Path

# Make sure the repository root (parent of this `tests` package) is on
# sys.path, regardless of the working directory the test runner was
# invoked from, so `import app...` resolves correctly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fail loudly (rather than silently writing to the real repo files) if
# `app.main` was already imported - and therefore already created its
# event-logger singleton against the *default* logs/events.log - before
# this package got a chance to redirect it.
if logging.getLogger("lead_intake_events").handlers:
    raise RuntimeError(
        "app.main was imported before the `tests` package could redirect "
        "logs/events.log to a temporary path. Run the suite as a package, "
        "e.g. `python -m unittest discover` from the repository root, not "
        "`python -m unittest discover -s tests`."
    )

TEST_DIR = Path(tempfile.mkdtemp(prefix="lead_intake_mvp_tests_"))
TEST_DB_PATH = TEST_DIR / "test_leads.db"
TEST_LOG_PATH = TEST_DIR / "test_events.log"

import app.database as database  # noqa: E402  (import must follow sys.path fix)
import app.logger as logger  # noqa: E402

database.DB_PATH = TEST_DB_PATH
logger.LOG_PATH = TEST_LOG_PATH


def _cleanup_test_dir() -> None:
    # On Windows, `rmtree` fails on an open file: the event logger's
    # FileHandler still holds `TEST_LOG_PATH` open at this point (logging
    # handlers are process-lifetime singletons, never closed by the app
    # itself), so it must be closed and detached before the directory that
    # contains it is removed.
    events_logger = logging.getLogger("lead_intake_events")
    for handler in list(events_logger.handlers):
        handler.close()
        events_logger.removeHandler(handler)

    shutil.rmtree(TEST_DIR)


atexit.register(_cleanup_test_dir)
