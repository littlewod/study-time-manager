from copy import deepcopy
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from ..errors import NotFoundError, ValidationError
from .repository import JsonRepository


class StudyService:
    def __init__(self, repository: JsonRepository):
        self.repository = repository

    def get_plan(self) -> dict[str, Any]:
        return self.repository.get_plan()

    def get_progress(self) -> dict[str, Any]:
        progress = self.repository.get_progress()
        progress.setdefault("schemaVersion", 2)
        progress.setdefault("updatedAt", None)
        progress.setdefault("completedTaskIds", [])
        progress.setdefault("notes", {})
        progress.setdefault("focusSessions", [])
        return progress

    def _task_index(self) -> dict[str, dict[str, Any]]:
        plan = self.get_plan()
        return {
            task["id"]: task
            for day in plan.get("days", [])
            for task in day.get("tasks", [])
        }

    def set_task_done(self, task_id: str, done: Any) -> dict[str, Any]:
        if not isinstance(done, bool):
            raise ValidationError("done必须是布尔值。")
        if task_id not in self._task_index():
            raise NotFoundError(f"任务不存在：{task_id}")

        progress = self.get_progress()
        completed = set(progress.get("completedTaskIds", []))
        if done:
            completed.add(task_id)
        else:
            completed.discard(task_id)
        progress["completedTaskIds"] = sorted(completed)
        progress["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.repository.save_progress(progress)
        return progress

    def set_note(self, task_id: str, note: Any) -> dict[str, Any]:
        if task_id not in self._task_index():
            raise NotFoundError(f"任务不存在：{task_id}")
        if not isinstance(note, str) or len(note) > 2_000:
            raise ValidationError("note必须是长度不超过2000的字符串。")
        progress = self.get_progress()
        notes = progress.setdefault("notes", {})
        if note.strip():
            notes[task_id] = note.strip()
        else:
            notes.pop(task_id, None)
        progress["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.repository.save_progress(progress)
        return progress

    @staticmethod
    def _parse_iso_datetime(value: Any, field: str) -> datetime:
        if not isinstance(value, str):
            raise ValidationError(f"{field}必须是ISO 8601时间字符串。")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(f"{field}不是有效的ISO 8601时间。") from exc

    def _validated_focus_session(
        self,
        value: Any,
        keep_id: bool = False,
        task_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValidationError("专注记录必须是JSON对象。")

        task_id = value.get("taskId")
        valid_task_ids = task_ids if task_ids is not None else set(self._task_index())
        if task_id is not None and task_id not in valid_task_ids:
            raise NotFoundError(f"任务不存在：{task_id}")

        duration_seconds = value.get("durationSec")
        if (
            not isinstance(duration_seconds, int)
            or isinstance(duration_seconds, bool)
            or not 1 <= duration_seconds <= 86_400
        ):
            raise ValidationError("durationSec必须是1到86400之间的整数。")

        started_at = self._parse_iso_datetime(value.get("startedAt"), "startedAt")
        ended_at = self._parse_iso_datetime(value.get("endedAt"), "endedAt")
        if (started_at.tzinfo is None) != (ended_at.tzinfo is None):
            raise ValidationError("startedAt与endedAt必须使用一致的时区格式。")
        if ended_at < started_at:
            raise ValidationError("endedAt不能早于startedAt。")

        day_value = value.get("date")
        try:
            date.fromisoformat(day_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("date必须是YYYY-MM-DD格式。") from exc

        session_id = value.get("id") if keep_id else None
        if not isinstance(session_id, str) or not session_id.strip():
            session_id = f"focus-{uuid4().hex[:12]}"

        return {
            "id": session_id,
            "taskId": task_id,
            "date": day_value,
            "startedAt": value["startedAt"],
            "endedAt": value["endedAt"],
            "durationSec": duration_seconds,
        }

    def add_focus_session(self, value: Any) -> dict[str, Any]:
        session = self._validated_focus_session(value)
        progress = self.get_progress()
        sessions = progress.setdefault("focusSessions", [])
        sessions.append(session)
        progress["focusSessions"] = sessions[-5_000:]
        progress["schemaVersion"] = 2
        progress["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.repository.save_progress(progress)
        return progress

    def replace_progress(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValidationError("进度必须是JSON对象。")

        task_ids = set(self._task_index())
        completed_value = value.get("completedTaskIds", [])
        if not isinstance(completed_value, list):
            raise ValidationError("completedTaskIds必须是数组。")
        completed = sorted({item for item in completed_value if item in task_ids})

        notes_value = value.get("notes", {})
        if not isinstance(notes_value, dict):
            raise ValidationError("notes必须是对象。")
        notes = {
            task_id: note.strip()
            for task_id, note in notes_value.items()
            if task_id in task_ids and isinstance(note, str) and note.strip() and len(note) <= 2_000
        }

        sessions_value = value.get("focusSessions", [])
        if not isinstance(sessions_value, list) or len(sessions_value) > 5_000:
            raise ValidationError("focusSessions必须是最多包含5000项的数组。")
        sessions = [
            self._validated_focus_session(item, keep_id=True, task_ids=task_ids)
            for item in sessions_value
        ]

        progress = {
            "schemaVersion": 2,
            "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "completedTaskIds": completed,
            "notes": notes,
            "focusSessions": sessions,
        }
        self.repository.save_progress(progress)
        return progress

    def get_day(self, day_value: str | None = None) -> dict[str, Any]:
        selected = day_value or date.today().isoformat()
        plan = self.get_plan()
        day = next((item for item in plan.get("days", []) if item.get("date") == selected), None)
        if day is None:
            return {"date": selected, "day": None, "progress": self.get_progress()}
        return {"date": selected, "day": deepcopy(day), "progress": self.get_progress()}

    def get_week_for_day(self, day_value: str | None = None) -> dict[str, Any]:
        selected = day_value or date.today().isoformat()
        plan = self.get_plan()
        week = next(
            (item for item in plan.get("weeks", []) if item["start"] <= selected <= item["end"]),
            None,
        )
        if week is None:
            return {"date": selected, "week": None, "days": [], "progress": self.get_progress()}
        days = [day for day in plan["days"] if week["start"] <= day["date"] <= week["end"]]
        return {"date": selected, "week": deepcopy(week), "days": deepcopy(days), "progress": self.get_progress()}
