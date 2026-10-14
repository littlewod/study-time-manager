import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import date, datetime
from tkinter import messagebox
from typing import Callable

from .config import Settings
from .planning.service import StudyService


COLORS = {
    "bg": "#07111F",
    "surface": "#0E1B2E",
    "surface_raised": "#14243B",
    "surface_soft": "#1A2E49",
    "done": "#0B1727",
    "text": "#F7FAFF",
    "text_soft": "#DFE8F5",
    "muted": "#9DAFC5",
    "line": "#2B4262",
    "mint": "#6EE7B7",
    "blue": "#8CB4FF",
    "amber": "#F6CF83",
    "danger": "#FF9AAA",
    "danger_soft": "#3A1D2A",
}

CATEGORY_COLORS = {
    "数学": "#83ADFF",
    "数据结构": "#A994FF",
    "英语": "#F5C978",
    "AI实操": "#6CE0B3",
    "LeetCode": "#FF9C84",
}

FONT = "Microsoft YaHei UI"
WEEKDAYS = "一二三四五六日"


class StudyWidget:
    def __init__(self, root: tk.Tk, settings: Settings, service: StudyService):
        self.root = root
        self.settings = settings
        self.service = service
        self.collapsed = False
        self._closing = False
        self._clock_after_id = None
        self._poll_after_id = None
        self._structure_key = None
        self._completed: set[str] = set()
        self._focus_sessions: list[dict] = []
        self._current_day: dict | None = None
        self._task_widgets: dict[str, dict] = {}
        self._task_fonts: list[tkfont.Font] = []
        self._configure_window()
        self._build_shell()
        self._tick_clock()
        self._poll_data()

    def _configure_window(self) -> None:
        self.root.title("研途 · 今日学习卡")
        icon_path = self.settings.app_dir / "assets" / "study-card.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        self.root.configure(bg=COLORS["bg"])
        self.root.attributes("-topmost", True)
        self._configure_display_scaling()
        self.root.minsize(self._px(400), self._px(88))
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.bind("<Escape>", lambda _event: self.root.iconify())
        self.root.bind("<Control-r>", lambda _event: self._poll_data(schedule=False))
        self.root.bind("<Control-o>", lambda _event: self.open_web())
        self.root.bind("<Control-q>", lambda _event: self.close_app())
        screen_height = self.root.winfo_screenheight()
        screen_width = self.root.winfo_screenwidth()
        self.expanded_width = min(self._px(448), max(self._px(400), screen_width - self._px(40)))
        self.expanded_height = min(self._px(760), max(self._px(540), screen_height - self._px(72)))
        self._place_top_right(self.expanded_width, self.expanded_height)

    def _configure_display_scaling(self) -> None:
        """Match Tk's point scaling to the actual monitor DPI."""
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except (tk.TclError, TypeError, ValueError):
            dpi = 96.0
        self.display_scale = max(1.0, min(dpi / 96.0, 3.0))
        self.root.tk.call("tk", "scaling", dpi / 72.0)

    def _px(self, value: int) -> int:
        return max(1, round(value * self.display_scale))

    def _place_top_right(self, width: int, height: int) -> None:
        self.root.update_idletasks()
        x = max(self._px(16), self.root.winfo_screenwidth() - width - self._px(20))
        y = self._px(20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_shell(self) -> None:
        header = tk.Frame(self.root, bg=COLORS["surface"], padx=16, pady=13)
        header.pack(fill="x")

        brand_mark = tk.Label(
            header, text="研", width=2, height=1, bg=COLORS["mint"], fg="#06140F",
            font=(FONT, 13, "bold"), padx=3, pady=5
        )
        brand_mark.pack(side="left", anchor="n")

        heading = tk.Frame(header, bg=COLORS["surface"])
        heading.pack(side="left", fill="x", expand=True, padx=(10, 8))
        tk.Label(
            heading, text="今日学习", bg=COLORS["surface"], fg=COLORS["text"],
            font=(FONT, 12, "bold"), anchor="w"
        ).pack(fill="x")
        self.date_label = tk.Label(
            heading, text="", bg=COLORS["surface"], fg=COLORS["muted"],
            font=(FONT, 9), anchor="w"
        )
        self.date_label.pack(fill="x", pady=(2, 0))

        actions = tk.Frame(header, bg=COLORS["surface"])
        actions.pack(side="right")
        self.clock_label = tk.Label(
            actions, text="--:--", bg=COLORS["surface"], fg=COLORS["text_soft"],
            font=(FONT, 14, "bold"), anchor="e"
        )
        self.clock_label.pack(side="left", padx=(0, 8))
        self.collapse_button = self._button(actions, "收起", self.toggle_collapse, compact=True)
        self.collapse_button.pack(side="left", padx=(0, 5))
        self._button(actions, "最小化", self.root.iconify, compact=True).pack(side="left", padx=(0, 5))
        self._button(
            actions, "退出", self.close_app, compact=True, danger=True
        ).pack(side="left")

        self.body = tk.Frame(self.root, bg=COLORS["bg"], padx=12, pady=0)
        self.body.pack(fill="both", expand=True)

        summary = tk.Frame(
            self.body, bg=COLORS["surface_raised"], padx=15, pady=13,
            highlightthickness=1, highlightbackground=COLORS["line"]
        )
        summary.pack(fill="x", pady=(12, 10))
        tk.Label(
            summary, text="今日重点", bg=COLORS["surface_raised"], fg=COLORS["mint"],
            font=(FONT, 9, "bold"), anchor="w"
        ).pack(fill="x")
        self.focus_label = tk.Label(
            summary, text="", bg=COLORS["surface_raised"], fg=COLORS["text"],
            font=(FONT, 14, "bold"), anchor="w", wraplength=self._px(382), justify="left"
        )
        self.focus_label.pack(fill="x", pady=(4, 8))

        summary_meta = tk.Frame(summary, bg=COLORS["surface_raised"])
        summary_meta.pack(fill="x")
        self.progress_label = tk.Label(
            summary_meta, text="", bg=COLORS["surface_raised"], fg=COLORS["mint"],
            font=(FONT, 10, "bold"), anchor="w"
        )
        self.progress_label.pack(side="left")
        self.remaining_label = tk.Label(
            summary_meta, text="", bg=COLORS["surface_raised"], fg=COLORS["muted"],
            font=(FONT, 10), anchor="e"
        )
        self.remaining_label.pack(side="right")

        self.progress_track = tk.Frame(summary, bg=COLORS["surface_soft"], height=7)
        self.progress_track.pack(fill="x", pady=(8, 0))
        self.progress_track.pack_propagate(False)
        self.progress_fill = tk.Frame(self.progress_track, bg=COLORS["mint"])
        self.progress_fill.place(x=0, y=0, relwidth=0, relheight=1)

        list_heading = tk.Frame(self.body, bg=COLORS["bg"])
        list_heading.pack(fill="x", pady=(2, 7))
        tk.Label(
            list_heading, text="任务清单", bg=COLORS["bg"], fg=COLORS["text_soft"],
            font=(FONT, 11, "bold"), anchor="w"
        ).pack(side="left")
        self.list_count_label = tk.Label(
            list_heading, text="", bg=COLORS["bg"], fg=COLORS["muted"],
            font=(FONT, 9), anchor="e"
        )
        self.list_count_label.pack(side="right")

        list_shell = tk.Frame(self.body, bg=COLORS["bg"])
        list_shell.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            list_shell, bg=COLORS["bg"], highlightthickness=0, takefocus=True
        )
        self.scrollbar = tk.Scrollbar(list_shell, orient="vertical", command=self.canvas.yview)
        self.task_frame = tk.Frame(self.canvas, bg=COLORS["bg"])
        self.task_window = self.canvas.create_window((0, 0), window=self.task_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.task_frame.bind(
            "<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda event: self.canvas.itemconfigure(self.task_window, width=event.width)
        )
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.canvas.bind("<Up>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Down>", lambda _event: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<Prior>", lambda _event: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _event: self.canvas.yview_scroll(1, "pages"))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.footer = tk.Frame(self.root, bg=COLORS["surface"], padx=14, pady=9)
        self.footer.pack(fill="x")
        self.status_label = tk.Label(
            self.footer, text="正在同步…", bg=COLORS["surface"], fg=COLORS["muted"],
            font=(FONT, 9), anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self._button(self.footer, "完整视图", self.open_web).pack(side="right")

    def _button(
        self,
        parent,
        text: str,
        command: Callable,
        compact: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        background = COLORS["danger_soft"] if danger else COLORS["surface_soft"]
        foreground = COLORS["danger"] if danger else COLORS["text_soft"]
        return tk.Button(
            parent, text=text, command=command, bg=background, fg=foreground,
            activebackground=COLORS["danger"] if danger else COLORS["line"],
            activeforeground=COLORS["bg"] if danger else COLORS["text"], bd=0,
            relief="flat", padx=7 if compact else 11, pady=5 if compact else 7,
            font=(FONT, 9 if compact else 10, "bold"), cursor="hand2", takefocus=True,
            highlightthickness=1,
            highlightbackground=COLORS["danger"] if danger else COLORS["line"],
            highlightcolor=COLORS["danger"] if danger else COLORS["blue"],
        )

    def close_app(self) -> None:
        """Stop background refreshes and fully close the desktop card."""
        if self._closing:
            return
        self._closing = True
        for after_id in (self._clock_after_id, self._poll_after_id):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        self.root.destroy()

    def _bind_mousewheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.footer.pack_forget()
            self.collapse_button.configure(text="展开")
            self._place_top_right(self.expanded_width, self._px(88))
        else:
            self.body.pack(fill="both", expand=True)
            self.footer.pack(fill="x")
            self.collapse_button.configure(text="收起")
            self._place_top_right(self.expanded_width, self.expanded_height)

    def open_web(self) -> None:
        webbrowser.open(f"http://{self.settings.host}:{self.settings.port}/")

    def _toggle(self, task_id: str) -> None:
        done = task_id not in self._completed
        widget = self._task_widgets.get(task_id, {}).get("button")
        if widget:
            widget.configure(state="disabled")
        self.status_label.configure(text="正在保存…", fg=COLORS["blue"])
        self.root.update_idletasks()
        try:
            progress = self.service.set_task_done(task_id, done)
            self._completed = set(progress.get("completedTaskIds", []))
            self._sync_task_states()
            self._update_summary()
            self.status_label.configure(
                text=f"已保存 · {datetime.now():%H:%M:%S}", fg=COLORS["mint"]
            )
        except Exception as exc:
            self.status_label.configure(text="保存失败，请重试", fg=COLORS["danger"])
            if widget:
                widget.configure(state="normal")
            messagebox.showerror("保存失败", str(exc))

    def _render_tasks(self, day: dict | None) -> None:
        scroll_position = self.canvas.yview()[0] if self.task_frame.winfo_children() else 0
        for child in self.task_frame.winfo_children():
            child.destroy()
        self._task_widgets.clear()
        self._task_fonts.clear()

        if day is None:
            tk.Label(
                self.task_frame, text="今天不在当前计划范围内\n打开完整视图查看长期路线",
                bg=COLORS["bg"], fg=COLORS["muted"], justify="center",
                font=(FONT, 11), pady=48
            ).pack(fill="x")
            return

        for task in day.get("tasks", []):
            category = task["category"]
            accent = CATEGORY_COLORS.get(category, COLORS["blue"])
            row = tk.Frame(
                self.task_frame, bg=COLORS["surface"], padx=0, pady=0,
                highlightthickness=1, highlightbackground=COLORS["line"]
            )
            row.pack(fill="x", pady=(0, 8))
            rail = tk.Frame(row, bg=accent, width=4)
            rail.pack(side="left", fill="y")
            rail.pack_propagate(False)

            content = tk.Frame(row, bg=COLORS["surface"], padx=11, pady=10)
            content.pack(side="left", fill="both", expand=True)
            check = tk.Button(
                content, text="", command=lambda tid=task["id"]: self._toggle(tid),
                width=2, height=1, bd=0, relief="flat", cursor="hand2", takefocus=True,
                font=(FONT, 11, "bold"), highlightthickness=1,
                highlightbackground=COLORS["line"], highlightcolor=COLORS["blue"]
            )
            check.pack(side="left", anchor="n", padx=(0, 10), pady=(1, 0))

            text_box = tk.Frame(content, bg=COLORS["surface"])
            text_box.pack(side="left", fill="x", expand=True)
            meta = tk.Label(
                text_box, text=f'{category}  ·  {task["durationMin"]} 分钟',
                bg=COLORS["surface"], fg=accent, font=(FONT, 9, "bold"),
                anchor="w", justify="left"
            )
            meta.pack(fill="x")
            normal_font = tkfont.Font(family=FONT, size=11, weight="bold")
            done_font = tkfont.Font(family=FONT, size=11, weight="bold", overstrike=True)
            self._task_fonts.extend([normal_font, done_font])
            title = tk.Label(
                text_box, text=task["title"], bg=COLORS["surface"], fg=COLORS["text_soft"],
                font=normal_font, anchor="w", justify="left", wraplength=self._px(326)
            )
            title.pack(fill="x", pady=(3, 0))
            self._task_widgets[task["id"]] = {
                "row": row,
                "rail": rail,
                "content": content,
                "text_box": text_box,
                "meta": meta,
                "title": title,
                "button": check,
                "normal_font": normal_font,
                "done_font": done_font,
            }

        self.root.update_idletasks()
        self.canvas.yview_moveto(scroll_position)

    def _sync_task_states(self) -> None:
        for task_id, widgets in self._task_widgets.items():
            done = task_id in self._completed
            bg = COLORS["done"] if done else COLORS["surface"]
            widgets["row"].configure(bg=bg)
            widgets["content"].configure(bg=bg)
            widgets["text_box"].configure(bg=bg)
            widgets["meta"].configure(bg=bg)
            widgets["title"].configure(
                bg=bg,
                fg=COLORS["muted"] if done else COLORS["text_soft"],
                font=widgets["done_font"] if done else widgets["normal_font"],
            )
            widgets["button"].configure(
                text="✓" if done else "",
                bg=COLORS["mint"] if done else COLORS["surface_soft"],
                fg="#06140F" if done else COLORS["text"],
                activebackground=COLORS["mint"] if done else COLORS["line"],
                activeforeground="#06140F" if done else COLORS["text"],
                state="normal",
            )

    def _update_summary(self) -> None:
        day = self._current_day
        tasks = day.get("tasks", []) if day else []
        done = sum(task["id"] in self._completed for task in tasks)
        total = len(tasks)
        remaining_minutes = sum(
            task["durationMin"] for task in tasks if task["id"] not in self._completed
        )
        today_value = date.today().isoformat()
        focused_minutes = round(sum(
            int(session.get("durationSec", 0))
            for session in self._focus_sessions
            if session.get("date") == today_value
        ) / 60)
        percentage = done / total if total else 0
        self.focus_label.configure(text=day["focus"] if day else "当前计划范围外")
        self.progress_label.configure(text=f"今日完成 {done}/{total}" if total else "今日无计划任务")
        self.remaining_label.configure(
            text=f"剩余 {remaining_minutes} 分钟 · 已专注 {focused_minutes} 分钟" if total else ""
        )
        self.list_count_label.configure(text=f"{total - done} 项待完成" if total else "")
        self.progress_fill.place_configure(relwidth=percentage)

    def _tick_clock(self) -> None:
        now = datetime.now()
        weekday = WEEKDAYS[now.weekday()]
        self.clock_label.configure(text=now.strftime("%H:%M"))
        self.date_label.configure(text=f"{now.month}月{now.day}日  星期{weekday}")
        if not self._closing:
            self._clock_after_id = self.root.after(1_000, self._tick_clock)

    def _poll_data(self, schedule: bool = True) -> None:
        try:
            today = date.today().isoformat()
            payload = self.service.get_day(today)
            day = payload["day"]
            completed = set(payload["progress"].get("completedTaskIds", []))
            focus_sessions = payload["progress"].get("focusSessions", [])
            task_ids = tuple(task["id"] for task in day.get("tasks", [])) if day else ()
            structure_key = (today, task_ids)
            self._current_day = day
            self._completed = completed
            self._focus_sessions = focus_sessions
            if structure_key != self._structure_key:
                self._render_tasks(day)
                self._structure_key = structure_key
            self._sync_task_states()
            self._update_summary()
            if not self.status_label.cget("text").startswith("已保存"):
                self.status_label.configure(text="同步正常 · 每 5 秒刷新", fg=COLORS["muted"])
        except Exception as exc:
            self.status_label.configure(text=f"同步失败：{exc}", fg=COLORS["danger"])
        finally:
            if schedule and not self._closing:
                self._poll_after_id = self.root.after(self.settings.refresh_ms, self._poll_data)
