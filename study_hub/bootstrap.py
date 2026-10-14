import json
import os
import tempfile
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Settings


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _shift_iso(value: str, days: int) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return value
    return (parsed + timedelta(days=days)).isoformat()


def _dated_sample(plan: dict[str, Any], start: date) -> dict[str, Any]:
    result = deepcopy(plan)
    source_start = datetime.strptime(result["meta"]["planStart"], "%Y-%m-%d").date()
    offset = (start - source_start).days
    result["meta"]["id"] = f"sample-study-plan-{start.isoformat()}"
    result["meta"]["planStart"] = _shift_iso(result["meta"]["planStart"], offset)
    result["meta"]["planEnd"] = _shift_iso(result["meta"]["planEnd"], offset)
    for week in result.get("weeks", []):
        week["start"] = _shift_iso(week["start"], offset)
        week["end"] = _shift_iso(week["end"], offset)
    for day_item in result.get("days", []):
        day_item["date"] = _shift_iso(day_item["date"], offset)
    for item in result.get("roadmap", []):
        item["start"] = _shift_iso(item.get("start", ""), offset)
        item["end"] = _shift_iso(item.get("end", ""), offset)
    return result


def default_progress() -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "updatedAt": None,
        "completedTaskIds": [],
        "notes": {},
        "focusSessions": [],
    }


def initialize_runtime_data(settings: Settings, today: date | None = None) -> None:
    """Create private runtime data from public examples on first launch."""
    if not settings.plan_path.exists():
        example_path = settings.app_dir / "examples" / "plan.example.json"
        with example_path.open("r", encoding="utf-8") as handle:
            example = json.load(handle)
        _write_json(settings.plan_path, _dated_sample(example, today or date.today()))

    if not settings.progress_path.exists():
        _write_json(settings.progress_path, default_progress())

    with settings.plan_path.open("r", encoding="utf-8") as handle:
        plan = json.load(handle)
    static_payload = "window.STUDY_PLAN = " + json.dumps(
        plan, ensure_ascii=False, separators=(",", ":")
    ) + ";\n"
    _atomic_write_text(settings.static_plan_path, static_payload)
