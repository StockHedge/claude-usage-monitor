"""tkinter 팝업 UI + 설정 창.

- 왼쪽에 Claude 픽셀 캐릭터 아이콘, 오른쪽에 '5시간 사용량 : N%'.
- 무테(overrideredirect) + 항상 위(topmost) + 반투명. 드래그 이동.
- 우클릭 메뉴: 지금 새로고침 / 설정 / 위치 초기화 / 종료.
- 설정 창에서 색상·크기·요금제·임계값·투명도·갱신주기를 수정하면 즉시 반영된다.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import colorchooser

from .config import PLAN_CEILINGS, Config, load as load_config, save as save_config
from .provider import UsageProvider, UsageSnapshot

log = logging.getLogger(__name__)

# Claude 픽셀 캐릭터 오마주. 1=몸통, 2=눈.
CLAUDE_MATRIX = [
    [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1],
    [1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
]

# (config 키, 표시 라벨)
PLAN_LABELS = [("pro", "Pro"), ("max5x", "Max 5x"), ("max20x", "Max 20x")]


class MonitorApp:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.provider = UsageProvider(cfg)
        self._alive = True
        self._last_snap: "UsageSnapshot | None" = None
        self._settings_win: "tk.Toplevel | None" = None

        self.root = tk.Tk()
        self.root.title("Claude 5h Usage")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=cfg.color_bg)
        self._set_opacity()

        self.frame = tk.Frame(self.root, bg=cfg.color_bg)
        self.frame.pack()
        self.icon = tk.Canvas(self.frame, highlightthickness=0, bd=0, bg=cfg.color_bg)
        self.label = tk.Label(
            self.frame, text="5시간 사용량 : …",
            font=(cfg.font_family, cfg.font_size, "bold"),
            bg=cfg.color_bg, fg=cfg.color_dim,
        )
        self._build_layout()

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="지금 새로고침", command=self._refresh_now)
        self.menu.add_command(label="설정…", command=self.open_settings)
        self.menu.add_command(label="위치 초기화", command=self._reset_position)
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=self._quit)

        self._drag: dict = {}
        self._bind_events()
        self._place_window()
        self.root.after(200, self._schedule_poll)

    # ---------- 외형 ----------
    def _set_opacity(self) -> None:
        try:
            self.root.attributes("-alpha", self.cfg.opacity)
        except tk.TclError:
            pass

    def _draw_icon(self) -> None:
        rows, cols = len(CLAUDE_MATRIX), len(CLAUDE_MATRIX[0])
        cell = max(2, round(self.cfg.icon_size / rows))
        self.icon.config(width=cols * cell, height=rows * cell, bg=self.cfg.color_bg)
        self.icon.delete("all")
        for r, row in enumerate(CLAUDE_MATRIX):
            for c, val in enumerate(row):
                if not val:
                    continue
                color = "#111111" if val == 2 else self.cfg.icon_color
                x0, y0 = c * cell, r * cell
                self.icon.create_rectangle(x0, y0, x0 + cell, y0 + cell,
                                           fill=color, outline=color)

    def _build_layout(self) -> None:
        self.icon.pack_forget()
        self.label.pack_forget()
        if self.cfg.show_icon:
            self._draw_icon()
            self.icon.pack(side="left", padx=(8, 4), pady=4)
            self.label.pack(side="left", padx=(0, 10), pady=4)
        else:
            self.label.pack(side="left", padx=10, pady=4)

    def apply_config(self) -> None:
        """설정 변경을 실행 중 UI에 즉시 반영하고 저장."""
        self._set_opacity()
        self.root.configure(bg=self.cfg.color_bg)
        self.frame.configure(bg=self.cfg.color_bg)
        self.label.configure(
            font=(self.cfg.font_family, self.cfg.font_size, "bold"),
            bg=self.cfg.color_bg,
        )
        self._build_layout()
        if self._last_snap is not None:
            self._apply(self._last_snap)
        save_config(self.cfg)

    # ---------- 위치/드래그 ----------
    def _place_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        screen_w = self.root.winfo_screenwidth()
        if self.cfg.window_x is not None and self.cfg.window_y is not None:
            x, y = self.cfg.window_x, self.cfg.window_y
        else:
            x, y = screen_w - width - 24, 24
        self.root.geometry(f"+{x}+{y}")

    def _bind_events(self) -> None:
        for widget in (self.root, self.frame, self.icon, self.label):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
            widget.bind("<Button-3>", self._on_menu)

    def _on_press(self, event) -> None:
        self._drag = {
            "x": event.x_root, "y": event.y_root,
            "ox": self.root.winfo_x(), "oy": self.root.winfo_y(), "moved": False,
        }

    def _on_drag(self, event) -> None:
        if not self._drag:
            return
        dx = event.x_root - self._drag["x"]
        dy = event.y_root - self._drag["y"]
        if abs(dx) > 2 or abs(dy) > 2:
            self._drag["moved"] = True
        self.root.geometry(f"+{self._drag['ox'] + dx}+{self._drag['oy'] + dy}")

    def _on_release(self, event) -> None:
        if self._drag.get("moved"):
            self.cfg.window_x = self.root.winfo_x()
            self.cfg.window_y = self.root.winfo_y()
            save_config(self.cfg)

    def _on_menu(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _reset_position(self) -> None:
        self.cfg.window_x = None
        self.cfg.window_y = None
        save_config(self.cfg)
        self._place_window()

    def _quit(self) -> None:
        self._alive = False
        try:
            self.cfg.window_x = self.root.winfo_x()
            self.cfg.window_y = self.root.winfo_y()
            save_config(self.cfg)
        except tk.TclError:
            pass
        self.root.destroy()

    # ---------- 폴링 ----------
    def _schedule_poll(self) -> None:
        if not self._alive:
            return
        threading.Thread(target=self._poll_worker, daemon=True).start()
        self.root.after(max(5, self.cfg.poll_interval_sec) * 1000, self._schedule_poll)

    def _refresh_now(self) -> None:
        threading.Thread(target=self._poll_worker, daemon=True).start()

    def _poll_worker(self) -> None:
        try:
            snap = self.provider.get()
        except Exception as exc:
            log.exception("폴링 실패")
            snap = UsageSnapshot(None, "unavailable", detail=str(exc))
        try:
            self.root.after(0, self._apply, snap)
        except RuntimeError:
            pass

    def _apply(self, snap: UsageSnapshot) -> None:
        self._last_snap = snap
        if snap.percent is None:
            self.label.config(text="5시간 사용량 : --", fg=self.cfg.color_dim)
            return
        prefix = "~" if snap.source == "estimate" else ""
        suffix = " ·" if snap.stale else ""
        value = int(round(snap.percent))
        self.label.config(text=f"5시간 사용량 : {prefix}{value}%{suffix}")
        if snap.percent >= self.cfg.danger_percent:
            self.label.config(fg=self.cfg.color_danger)
        elif snap.percent >= self.cfg.warn_percent:
            self.label.config(fg=self.cfg.color_warn)
        else:
            self.label.config(fg=self.cfg.color_normal)

    # ---------- 설정 창 ----------
    def open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        SettingsWindow(self)

    def run(self) -> None:
        self.root.mainloop()


class SettingsWindow:
    """실행 중 설정 편집 창. 저장 시 MonitorApp.apply_config로 즉시 반영."""

    COLOR_FIELDS = [
        ("color_bg", "배경색"),
        ("color_normal", "정상색"),
        ("color_warn", "주의색"),
        ("color_danger", "위험색"),
        ("icon_color", "아이콘색"),
    ]

    def __init__(self, app: MonitorApp):
        self.app = app
        self.cfg = app.cfg
        win = tk.Toplevel(app.root)
        app._settings_win = win
        self.win = win
        win.title("설정")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(padx=14, pady=12)
        win.protocol("WM_DELETE_WINDOW", self._close)

        self._colors = {key: tk.StringVar(value=getattr(self.cfg, key))
                        for key, _ in self.COLOR_FIELDS}
        row = 0

        tk.Label(win, text="요금제").grid(row=row, column=0, sticky="w", pady=3)
        self.plan_var = tk.StringVar(value=self._plan_label(self.cfg.plan))
        tk.OptionMenu(win, self.plan_var, *[lbl for _, lbl in PLAN_LABELS]).grid(
            row=row, column=1, sticky="ew")
        row += 1

        self.show_icon_var = tk.BooleanVar(value=self.cfg.show_icon)
        tk.Checkbutton(win, text="Claude 캐릭터 아이콘 표시", variable=self.show_icon_var).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1

        self.font_size_var = tk.IntVar(value=self.cfg.font_size)
        row = self._spin(win, "글자 크기", self.font_size_var, 8, 20, row)
        self.icon_size_var = tk.IntVar(value=self.cfg.icon_size)
        row = self._spin(win, "아이콘 크기", self.icon_size_var, 14, 44, row)

        tk.Label(win, text="투명도").grid(row=row, column=0, sticky="w", pady=3)
        self.opacity_var = tk.DoubleVar(value=self.cfg.opacity)
        tk.Scale(win, from_=0.4, to=1.0, resolution=0.02, orient="horizontal",
                 variable=self.opacity_var).grid(row=row, column=1, sticky="ew")
        row += 1

        self.warn_var = tk.IntVar(value=int(self.cfg.warn_percent))
        row = self._spin(win, "주의 임계값 %", self.warn_var, 0, 100, row)
        self.danger_var = tk.IntVar(value=int(self.cfg.danger_percent))
        row = self._spin(win, "위험 임계값 %", self.danger_var, 0, 100, row)
        self.poll_var = tk.IntVar(value=self.cfg.poll_interval_sec)
        row = self._spin(win, "갱신 주기(초)", self.poll_var, 30, 600, row)

        for key, text in self.COLOR_FIELDS:
            row = self._color_row(win, text, key, row)

        btns = tk.Frame(win)
        btns.grid(row=row, column=0, columnspan=2, pady=(12, 0))
        tk.Button(btns, text="저장", width=10, command=self._save).pack(side="left", padx=4)
        tk.Button(btns, text="취소", width=10, command=self._close).pack(side="left", padx=4)

        win.columnconfigure(1, weight=1)
        win.transient(app.root)
        win.lift()

    def _spin(self, win, text, var, lo, hi, row) -> int:
        tk.Label(win, text=text).grid(row=row, column=0, sticky="w", pady=3)
        tk.Spinbox(win, from_=lo, to=hi, textvariable=var, width=8).grid(
            row=row, column=1, sticky="w")
        return row + 1

    def _color_row(self, win, text, key, row) -> int:
        tk.Label(win, text=text).grid(row=row, column=0, sticky="w", pady=3)
        holder = tk.Frame(win)
        holder.grid(row=row, column=1, sticky="w")
        swatch = tk.Label(holder, width=3, bg=self._colors[key].get(), relief="solid", bd=1)
        swatch.pack(side="left", padx=(0, 6))

        def pick():
            chosen = colorchooser.askcolor(color=self._colors[key].get(), parent=win)
            if chosen and chosen[1]:
                self._colors[key].set(chosen[1])
                swatch.config(bg=chosen[1])

        tk.Button(holder, text="선택", command=pick).pack(side="left")
        return row + 1

    @staticmethod
    def _plan_label(key: str) -> str:
        for k, lbl in PLAN_LABELS:
            if k == key:
                return lbl
        return "Max 5x"

    @staticmethod
    def _plan_key(label: str) -> str:
        for k, lbl in PLAN_LABELS:
            if lbl == label:
                return k
        return "max5x"

    def _close(self) -> None:
        self.app._settings_win = None
        self.win.destroy()

    def _save(self) -> None:
        cfg = self.cfg
        cfg.apply_plan(self._plan_key(self.plan_var.get()))
        cfg.show_icon = bool(self.show_icon_var.get())
        cfg.font_size = int(self.font_size_var.get())
        cfg.icon_size = int(self.icon_size_var.get())
        cfg.opacity = float(self.opacity_var.get())
        cfg.warn_percent = float(self.warn_var.get())
        cfg.danger_percent = float(self.danger_var.get())
        cfg.poll_interval_sec = int(self.poll_var.get())
        for key, var in self._colors.items():
            setattr(cfg, key, var.get())
        self.app.apply_config()
        self._close()


def main() -> None:
    from .logsetup import setup_logging

    setup_logging()
    log.info("모니터 시작")
    cfg = load_config()
    MonitorApp(cfg).run()
