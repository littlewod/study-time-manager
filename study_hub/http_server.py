import json
import logging
import threading
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .config import Settings
from .errors import AppError, ValidationError
from .planning.service import StudyService


LOGGER = logging.getLogger("study_hub")


class StudyRequestHandler(SimpleHTTPRequestHandler):
    server_version = "StudyHub/1.1"

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    @property
    def service(self) -> StudyService:
        return self.server.study_service  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        LOGGER.info("http_request", extra={"message_text": fmt % args})

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-Id", self.request_id)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        content_length = self.headers.get("Content-Length")
        if not content_length:
            raise ValidationError("请求体不能为空。")
        try:
            length = int(content_length)
            if not 0 < length <= 1_000_000:
                raise ValidationError("请求体大小必须在1MB以内。")
            raw = self.rfile.read(length)
            value = json.loads(raw.decode("utf-8"))
        except ValidationError:
            raise
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("请求体不是有效JSON。") from exc
        if not isinstance(value, dict):
            raise ValidationError("请求体必须是JSON对象。")
        return value

    def _problem(self, error: AppError) -> None:
        self._send_json(error.status, {
            "type": f"urn:study-hub:error:{error.code}",
            "title": error.title,
            "status": error.status,
            "detail": error.detail,
            "instance": self.path,
            "requestId": self.request_id,
        })

    def _dispatch(self, callback) -> None:
        self.request_id = uuid.uuid4().hex[:12]
        try:
            callback()
        except AppError as error:
            self._problem(error)
        except Exception:
            LOGGER.exception("unexpected_request_error", extra={"request_id": self.request_id})
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "type": "urn:study-hub:error:internal",
                "title": "Internal Error",
                "status": 500,
                "detail": "本地服务处理失败，请查看study-hub.log。",
                "instance": self.path,
                "requestId": self.request_id,
            })

    def do_GET(self) -> None:
        self._dispatch(self._do_get)

    def _do_get(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path == "/ready":
            self.service.get_plan()
            self.service.get_progress()
            self._send_json(200, {"status": "ready"})
            return
        if parsed.path == "/api/v1/plan":
            self._send_json(200, {"data": self.service.get_plan()})
            return
        if parsed.path == "/api/v1/progress":
            self._send_json(200, {"data": self.service.get_progress()})
            return
        if parsed.path == "/api/v1/today":
            selected = parse_qs(parsed.query).get("date", [None])[0]
            self._send_json(200, {"data": self.service.get_day(selected)})
            return
        if parsed.path == "/api/v1/week":
            selected = parse_qs(parsed.query).get("date", [None])[0]
            self._send_json(200, {"data": self.service.get_week_for_day(selected)})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_PATCH(self) -> None:
        self._dispatch(self._do_patch)

    def do_POST(self) -> None:
        self._dispatch(self._do_post)

    def do_PUT(self) -> None:
        self._dispatch(self._do_put)

    def _do_post(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/v1/focus-sessions":
            raise ValidationError("不支持的接口路径。")
        progress = self.service.add_focus_session(self._read_json())
        self._send_json(HTTPStatus.CREATED, {"data": progress})

    def _do_put(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/v1/progress":
            raise ValidationError("不支持的接口路径。")
        progress = self.service.replace_progress(self._read_json())
        self._send_json(200, {"data": progress})

    def _do_patch(self) -> None:
        parsed = urlparse(self.path)
        prefix = "/api/v1/tasks/"
        if not parsed.path.startswith(prefix):
            raise ValidationError("不支持的接口路径。")
        task_id = unquote(parsed.path[len(prefix):])
        if not task_id:
            raise ValidationError("任务ID不能为空。")
        body = self._read_json()
        if "done" in body:
            progress = self.service.set_task_done(task_id, body["done"])
        elif "note" in body:
            progress = self.service.set_note(task_id, body["note"])
        else:
            raise ValidationError("仅支持更新done或note字段。")
        self._send_json(200, {"data": progress})


class StudyHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, settings: Settings, service: StudyService):
        handler = lambda *args, **kwargs: StudyRequestHandler(
            *args, directory=str(settings.app_dir), **kwargs
        )
        super().__init__((settings.host, settings.port), handler)
        self.study_service = service


def start_server(settings: Settings, service: StudyService) -> tuple[StudyHttpServer, threading.Thread]:
    server = StudyHttpServer(settings, service)
    thread = threading.Thread(target=server.serve_forever, name="study-http", daemon=True)
    thread.start()
    return server, thread
