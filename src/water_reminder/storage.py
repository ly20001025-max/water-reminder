"""Small, local-only JSON storage with atomic replacement."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class JsonStore:
    """Read and atomically write one JSON object at ``path``.

    Missing files are treated as a fresh installation. Invalid JSON is moved
    aside so the application can start with defaults without destroying the
    user's original data.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.last_warning: str | None = None

    def load(self) -> dict[str, Any]:
        self.last_warning = None
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            return payload
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self.last_warning = f"Local data could not be read ({exc}); defaults were loaded."
            self._quarantine_corrupt_file()
            return {}

    def save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _quarantine_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self.path.with_name(f"{self.path.stem}.corrupt-{suffix}{self.path.suffix}")
        try:
            os.replace(self.path, destination)
        except OSError as exc:
            self.last_warning = f"{self.last_warning} The damaged file could not be moved aside ({exc})."
