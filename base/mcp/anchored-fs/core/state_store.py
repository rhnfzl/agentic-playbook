"""JSON state file I/O with portalocker advisory locks + atomic writes."""

from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

import portalocker


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default if default is not None else {}
        with portalocker.Lock(  # pyright: ignore[reportAttributeAccessIssue]  # justification: portalocker exports Lock at runtime; the installed build's type info omits it
            str(self.path),
            mode="r",
            flags=portalocker.LOCK_SH,  # pyright: ignore[reportAttributeAccessIssue]  # justification: portalocker exports LOCK_SH at runtime; the installed build's type info omits it
            timeout=5,
        ) as fh:
            content = fh.read()
            if not content.strip():
                return default if default is not None else {}
            return json.loads(content)

    def write(self, data: Any) -> None:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def update(self, fn: Callable[[Any], Any]) -> None:
        current = self.read()
        updated = fn(current)
        self.write(updated)
