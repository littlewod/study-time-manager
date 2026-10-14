import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class JsonRepository:
    def __init__(self, plan_path: Path, progress_path: Path):
        self.plan_path = plan_path
        self.progress_path = progress_path
        self._lock = threading.RLock()

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def get_plan(self) -> dict[str, Any]:
        with self._lock:
            return self._read(self.plan_path)

    def get_progress(self) -> dict[str, Any]:
        with self._lock:
            return self._read(self.progress_path)

    def save_progress(self, progress: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(self.progress_path, progress)
