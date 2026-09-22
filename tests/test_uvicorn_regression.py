"""Real-Uvicorn network regression test for the generic-500 exception path.

`fastapi.testclient.TestClient` uses an in-process ASGI transport and does
not reproduce a real Starlette/Uvicorn defect: a handler registered via
`@app.exception_handler(Exception)` is routed to Starlette's outer
`ServerErrorMiddleware`, which sends that handler's response and then
*always* re-raises the original exception afterwards. Under real Uvicorn,
that re-raise lands in `RequestResponseCycle.run_asgi`'s except branch,
which unconditionally closes the transport whenever a response has already
started - racing the body write it just issued. The observed symptom is
500 response headers with a correct `Content-Length`, and zero bytes of
body ever delivered (see `app.main.catch_unhandled_exceptions` for the
fix and full explanation).

This module starts the real application in a subprocess through the
documented `uvicorn app.main:app` runtime (not a mock, not TestClient) and
makes a genuine HTTP request over a real socket, to prove the fix actually
holds end-to-end rather than only under TestClient's in-process transport.

Isolation: the subprocess's working directory is a fresh temporary
directory, so the relative `data/leads.db` / `logs/events.log` paths in
`app.database` / `app.logger` resolve inside it - the repository's real
`data/leads.db` and `logs/events.log` are never touched. No external
network calls are made; the server binds only to 127.0.0.1 on a freshly
selected free port.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import mkdtemp
from typing import Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standalone, non-package Uvicorn entrypoint for this test only. Written
# into the isolated temp dir at setUp time - deliberately NOT part of the
# `app` or `tests` package (importing it must not trigger
# `tests/__init__.py`'s own DB/log redirection, which is for the *parent*
# unittest process, not this subprocess). It adds one extra, undocumented
# route to the real, unmodified `app.main.app` instance purely to trigger a
# deterministic ordinary exception over a real HTTP connection.
ENTRYPOINT_SOURCE = '''\
from app.main import app


@app.get("/__test_trigger_unexpected_error__")
def _trigger_unexpected_error() -> None:
    raise RuntimeError("deterministic-test-trigger")
'''


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _rmtree_with_retry(path: Path, attempts: int = 10, delay: float = 0.2) -> None:
    """`shutil.rmtree` right after killing the subprocess.

    On Windows, a just-terminated process's open file handles (here: the
    subprocess's own `logs/events.log` FileHandler) can take a moment to be
    released by the OS even after `Popen.wait()` has returned, so the very
    next `rmtree` can hit a transient `PermissionError`. This retries with
    a short bounded backoff - narrowly scoped to that one error type - and
    still lets the final attempt raise, rather than silently swallowing
    unrelated cleanup failures.
    """
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


class UvicornRegressionTests(unittest.TestCase):
    """Spins up the real app under real Uvicorn in an isolated subprocess."""

    def setUp(self) -> None:
        self.temp_dir = Path(mkdtemp(prefix="lead_intake_mvp_uvicorn_regression_"))
        self.addCleanup(self._cleanup_temp_dir)

        entrypoint_path = self.temp_dir / "_regression_entrypoint.py"
        entrypoint_path.write_text(ENTRYPOINT_SOURCE, encoding="utf-8")

        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(REPO_ROOT) + os.pathsep + existing_pythonpath
            if existing_pythonpath
            else str(REPO_ROOT)
        )

        self._stdout_file = open(self.temp_dir / "uvicorn_stdout.log", "w", encoding="utf-8")
        self._stderr_file = open(self.temp_dir / "uvicorn_stderr.log", "w", encoding="utf-8")
        self.addCleanup(self._stdout_file.close)
        self.addCleanup(self._stderr_file.close)

        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "_regression_entrypoint:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=self.temp_dir,
            env=env,
            stdout=self._stdout_file,
            stderr=self._stderr_file,
        )
        self.addCleanup(self._terminate_process)

        self._wait_for_server_ready(timeout=15.0)

    def _terminate_process(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)

    def _cleanup_temp_dir(self) -> None:
        _rmtree_with_retry(self.temp_dir)

    def _wait_for_server_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.fail(
                    "Uvicorn subprocess exited early with code "
                    f"{self.proc.returncode}; see {self._stderr_file.name}"
                )
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except httpx.HTTPError as error:
                last_error = error
            time.sleep(0.1)
        self.fail(f"Uvicorn subprocess did not become ready in time: {last_error}")

    def test_unexpected_exception_returns_complete_json_500_over_real_http(self) -> None:
        try:
            response = httpx.get(
                f"{self.base_url}/__test_trigger_unexpected_error__", timeout=5.0
            )
        except httpx.TimeoutException:
            self.fail(
                "Real HTTP request to the generic-500 path timed out - this "
                "is exactly the incomplete-response defect this test guards "
                "against."
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("application/json", response.headers.get("content-type", ""))

        # The body must have arrived completely and match the intended
        # generic error shape exactly - not be empty/truncated.
        self.assertEqual(response.json(), {"detail": "Internal server error."})

        raw_text = response.text
        self.assertNotIn("RuntimeError", raw_text)
        self.assertNotIn("deterministic-test-trigger", raw_text)
        self.assertNotIn("Traceback", raw_text)


if __name__ == "__main__":
    unittest.main()
