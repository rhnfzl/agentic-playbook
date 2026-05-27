"""Exclusive non-blocking install lock (POSIX flock / Windows msvcrt).

Two parallel `make install` runs against the same target used to race on
the lockfile read-modify-write. With this lock the second installer
fails fast instead of corrupting `.playbook-lock.json`.

POSIX uses `fcntl.flock(LOCK_EX | LOCK_NB)`. Windows uses
`msvcrt.locking(LK_NBLCK)`; both are stdlib. Genuinely-locked-by-another
process raises RuntimeError with the lock file path; the lock is
advisory in both cases.

The acquired flag isolates the unlock + close path so a contention raise
during acquisition cannot mask itself by calling fileno() on an
already-closed handle in the outer finally block.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path


INSTALL_LOCK_NAME = ".playbook-install.lock"


@contextlib.contextmanager
def install_lock(lock_dir: Path):
    """Acquire an exclusive non-blocking file lock for the install path.

    Caller passes the directory where the lockfile lives (the install
    target, or REPO_ROOT for in-repo installs). On contention raises
    RuntimeError pointing at the lock file; on platforms without
    fcntl/msvcrt the lock degrades to a no-op so the install proceeds.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / INSTALL_LOCK_NAME

    fh = lock_path.open("a+")
    acquired = False

    try:
        if os.name == "nt":
            try:
                import msvcrt
            except ImportError:
                yield
                return
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                fh.close()
                raise RuntimeError(
                    f"Another playbook install is in progress against "
                    f"{lock_dir} (lock file: {lock_path}). Wait for it to "
                    f"finish, or remove the lock file if you're sure no "
                    f"process holds it."
                ) from None
        else:
            try:
                import fcntl
            except ImportError:
                yield
                return
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                fh.close()
                raise RuntimeError(
                    f"Another playbook install is in progress against "
                    f"{lock_dir} (lock file: {lock_path}). Wait for it to "
                    f"finish, or remove the lock file if you're sure no "
                    f"process holds it."
                ) from None
        acquired = True

        try:
            fh.seek(0)
            fh.truncate(0)
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        except OSError:
            pass
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    try:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl

                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                fh.close()
