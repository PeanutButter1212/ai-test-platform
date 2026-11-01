"""Start a fresh, isolated shop instance for a test run.

`ref=None` runs the current working tree; any git ref (e.g. the `shop-clean`
tag) is checked out into a temporary worktree first.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


class EnvError(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


@contextmanager
def shop_instance(ref: str | None = None, startup_timeout: float = 15):
    """Yield {'base_url', 'ref', 'commit', 'log', 'workdir'} for a healthy shop; raise EnvError otherwise."""
    tmp = Path(tempfile.mkdtemp(prefix="shop-env-"))
    workdir = ROOT
    worktree = None
    try:
        if ref:
            worktree = tmp / "src"
            try:
                _git("worktree", "add", "--detach", str(worktree), ref)
            except subprocess.CalledProcessError as exc:
                worktree = None
                raise EnvError(f"cannot check out {ref!r}: {exc.stderr.strip()}") from exc
            workdir = worktree
        commit = _git("-C", str(workdir), "rev-parse", "--short", "HEAD")
        if ref is None and _git("status", "--porcelain", "--", "shop"):
            commit += "+dirty"

        port = _free_port()
        log_path = tmp / "server.log"
        log = log_path.open("w")
        env = {"SHOP_DB": str(tmp / "shop.db"), "PATH": "/usr/bin:/bin"}
        app = "shop.app:app"
        if os.environ.get("SHOP_FLAKY"):  # simulated instability, see shop/chaos.py
            env["SHOP_FLAKY"], app = os.environ["SHOP_FLAKY"], "shop.chaos:app"
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", app, "--port", str(port)],
            cwd=workdir, stdout=log, stderr=subprocess.STDOUT, env=env,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            _wait_healthy(base_url, proc, startup_timeout, log_path)
            yield {"base_url": base_url, "ref": ref or "working-tree", "commit": commit, "log": log_path,
                   "workdir": workdir}
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            log.close()
    finally:
        if worktree:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT,
                           capture_output=True)


def _wait_healthy(base_url, proc, timeout, log_path):
    deadline = time.time() + timeout
    last = "no response"
    while time.time() < deadline:
        if proc.poll() is not None:
            raise EnvError(f"shop exited during startup (code {proc.returncode}):\n{log_path.read_text()[-800:]}")
        try:
            res = httpx.get(f"{base_url}/api/health", timeout=1)
            if res.status_code == 200 and res.json().get("products", 0) > 0:
                return
            last = f"health returned {res.status_code} {res.text[:100]}"
        except httpx.TransportError as exc:
            last = str(exc)
        time.sleep(0.2)
    raise EnvError(f"shop not healthy after {timeout}s: {last}")
