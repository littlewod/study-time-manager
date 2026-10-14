import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.request import Request, urlopen

from study_hub.bootstrap import initialize_runtime_data
from study_hub.config import Settings
from study_hub.errors import NotFoundError, ValidationError
from study_hub.http_server import StudyHttpServer
from study_hub.planning.repository import JsonRepository
from study_hub.planning.service import StudyService
from study_hub.widget import StudyWidget


class _FakeRoot:
    def __init__(self):
        self.cancelled = []
        self.destroy_count = 0

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)

    def destroy(self):
        self.destroy_count += 1


class StudyWidgetCloseTest(unittest.TestCase):
    def test_close_stops_callbacks_and_destroys_window_once(self):
        root = _FakeRoot()
        widget = StudyWidget.__new__(StudyWidget)
        widget.root = root
        widget._closing = False
        widget._clock_after_id = "clock"
        widget._poll_after_id = "poll"

        widget.close_app()
        widget.close_app()

        self.assertEqual(["clock", "poll"], root.cancelled)
        self.assertEqual(1, root.destroy_count)
        self.assertTrue(widget._closing)


class StudyServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        base = Path(self.temp_dir.name)
        plan = {
            "days": [{
                "date": "2026-10-12",
                "tasks": [{"id": "task-1", "title": "test", "durationMin": 30}],
            }],
            "weeks": [{"start": "2026-10-12", "end": "2026-10-18", "title": "week"}],
        }
        progress = {"completedTaskIds": [], "notes": {}, "updatedAt": None}
        (base / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (base / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
        repo = JsonRepository(base / "plan.json", base / "progress.json")
        self.service = StudyService(repo)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_toggle_task_is_persisted(self):
        result = self.service.set_task_done("task-1", True)
        self.assertEqual(["task-1"], result["completedTaskIds"])
        self.assertEqual(["task-1"], self.service.get_progress()["completedTaskIds"])

    def test_unknown_task_is_rejected(self):
        with self.assertRaises(NotFoundError):
            self.service.set_task_done("missing", True)

    def test_done_requires_boolean(self):
        with self.assertRaises(ValidationError):
            self.service.set_task_done("task-1", "yes")

    def test_day_and_week_queries(self):
        day = self.service.get_day("2026-10-12")
        week = self.service.get_week_for_day("2026-10-12")
        self.assertEqual("task-1", day["day"]["tasks"][0]["id"])
        self.assertEqual("week", week["week"]["title"])

    def test_focus_session_is_persisted(self):
        result = self.service.add_focus_session({
            "taskId": "task-1",
            "date": "2026-10-12",
            "startedAt": "2026-10-12T08:00:00+08:00",
            "endedAt": "2026-10-12T08:25:00+08:00",
            "durationSec": 1_500,
        })
        session = result["focusSessions"][0]
        self.assertEqual("task-1", session["taskId"])
        self.assertEqual(1_500, session["durationSec"])
        self.assertTrue(session["id"].startswith("focus-"))

    def test_invalid_focus_duration_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.add_focus_session({
                "taskId": "task-1",
                "date": "2026-10-12",
                "startedAt": "2026-10-12T08:00:00+08:00",
                "endedAt": "2026-10-12T08:00:00+08:00",
                "durationSec": 0,
            })

    def test_replace_progress_filters_unknown_tasks(self):
        result = self.service.replace_progress({
            "completedTaskIds": ["task-1", "missing"],
            "notes": {"task-1": " keep ", "missing": "drop"},
            "focusSessions": [],
        })
        self.assertEqual(["task-1"], result["completedTaskIds"])
        self.assertEqual({"task-1": "keep"}, result["notes"])


class StudyHttpServerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        base = Path(self.temp_dir.name)
        data_dir = base / "data"
        data_dir.mkdir()
        plan = {
            "days": [{
                "date": "2026-10-12",
                "tasks": [{"id": "task-1", "title": "test", "durationMin": 30}],
            }],
            "weeks": [{"start": "2026-10-12", "end": "2026-10-18", "title": "week"}],
        }
        progress = {"completedTaskIds": [], "notes": {}, "updatedAt": None}
        (data_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (data_dir / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
        settings = replace(Settings.from_app_dir(base), port=0)
        service = StudyService(JsonRepository(settings.plan_path, settings.progress_path))
        self.server = StudyHttpServer(settings, service)
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_health_and_patch_round_trip(self):
        with urlopen(f"{self.base_url}/health", timeout=2) as response:
            self.assertEqual("ok", json.load(response)["status"])

        request = Request(
            f"{self.base_url}/api/v1/tasks/task-1",
            data=json.dumps({"done": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        self.assertEqual(["task-1"], payload["data"]["completedTaskIds"])

        focus_request = Request(
            f"{self.base_url}/api/v1/focus-sessions",
            data=json.dumps({
                "taskId": "task-1",
                "date": "2026-10-12",
                "startedAt": "2026-10-12T08:00:00+08:00",
                "endedAt": "2026-10-12T08:25:00+08:00",
                "durationSec": 1_500,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(focus_request, timeout=2) as response:
            self.assertEqual(201, response.status)
            payload = json.load(response)
        self.assertEqual(1_500, payload["data"]["focusSessions"][0]["durationSec"])


class BootstrapTest(unittest.TestCase):
    def test_first_launch_creates_private_runtime_data(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            base = Path(temp_dir)
            examples = base / "examples"
            examples.mkdir()
            source = Path(__file__).parents[1] / "examples" / "plan.example.json"
            (examples / "plan.example.json").write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
            settings = Settings.from_app_dir(base)

            from datetime import date
            initialize_runtime_data(settings, date(2026, 10, 14))

            plan = json.loads(settings.plan_path.read_text(encoding="utf-8"))
            progress = json.loads(settings.progress_path.read_text(encoding="utf-8"))
            self.assertEqual("2026-10-14", plan["meta"]["planStart"])
            self.assertEqual([], progress["focusSessions"])
            self.assertTrue(settings.static_plan_path.read_text(encoding="utf-8").startswith("window.STUDY_PLAN = "))


if __name__ == "__main__":
    unittest.main()
