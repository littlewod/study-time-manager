import json
import logging
import os
import sys
import tkinter as tk
from pathlib import Path

from study_hub.bootstrap import initialize_runtime_data
from study_hub.config import Settings
from study_hub.http_server import start_server
from study_hub.planning.repository import JsonRepository
from study_hub.planning.service import StudyService
from study_hub.widget import StudyWidget


APP_DIR = Path(__file__).resolve().parent


def enable_high_dpi() -> None:
    """Keep the Tk window sharp when Windows display scaling is above 100%."""
    if os.name != "nt":
        return

    try:
        import ctypes

        # Per-monitor v2 gives Windows the best result on mixed-DPI displays.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    try:
        import ctypes

        # Windows 8.1 fallback.
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass

    try:
        import ctypes

        # Older Windows fallback.
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def configure_logging(app_dir: Path) -> None:
    logging.basicConfig(
        filename=app_dir / "study-hub.log",
        level=logging.INFO,
        encoding="utf-8",
        format='{"time":"%(asctime)s","level":"%(levelname)s","event":"%(message)s"}',
    )


def build_service(settings: Settings) -> StudyService:
    repository = JsonRepository(settings.plan_path, settings.progress_path)
    return StudyService(repository)


def run_check(settings: Settings, service: StudyService) -> int:
    plan = service.get_plan()
    progress = service.get_progress()
    today = service.get_day(plan["meta"]["planStart"])
    print(json.dumps({
        "status": "ok",
        "planId": plan["meta"]["id"],
        "days": len(plan["days"]),
        "todayTasks": len(today["day"]["tasks"]),
        "completed": len(progress.get("completedTaskIds", [])),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    enable_high_dpi()
    settings = Settings.from_app_dir(APP_DIR)
    configure_logging(APP_DIR)
    initialize_runtime_data(settings)
    service = build_service(settings)
    if "--check" in sys.argv:
        return run_check(settings, service)

    try:
        server, _thread = start_server(settings, service)
    except OSError as exc:
        logging.exception("server_start_failed")
        tk.Tk().withdraw()
        from tkinter import messagebox
        messagebox.showerror("启动失败", f"本地端口{settings.port}无法使用：{exc}")
        return 1

    root = tk.Tk()
    StudyWidget(root, settings, service)
    try:
        root.mainloop()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
