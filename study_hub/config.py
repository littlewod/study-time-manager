import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_dir: Path
    data_dir: Path
    plan_path: Path
    progress_path: Path
    static_plan_path: Path
    host: str = "127.0.0.1"
    port: int = 8765
    refresh_ms: int = 5_000

    @staticmethod
    def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} 必须是整数。") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间。")
        return value

    @classmethod
    def from_app_dir(cls, app_dir: Path) -> "Settings":
        resolved = app_dir.resolve()
        data_dir = resolved / "data"
        return cls(
            app_dir=resolved,
            data_dir=data_dir,
            plan_path=data_dir / "plan.json",
            progress_path=data_dir / "progress.json",
            static_plan_path=resolved / "plan-data.js",
            host=os.environ.get("STUDY_HUB_HOST", "127.0.0.1"),
            port=cls._int_env("STUDY_HUB_PORT", 8765, 1, 65_535),
            refresh_ms=cls._int_env("STUDY_HUB_REFRESH_MS", 5_000, 1_000, 60_000),
        )
