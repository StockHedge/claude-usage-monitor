"""tkinter 팝업 UI + 설정 창.

디자인: "픽셀 인스트루먼트 HUD"
- 따뜻한 다크 라운드 카드(모서리는 Windows -transparentcolor로 실제 둥글게).
- 왼쪽에 Claude 픽셀 캐릭터(브랜드), 오른쪽에 작은 '5시간 사용량' 라벨 + 큰 퍼센트 숫자.
- 시그니처: 픽셀 세그먼트 미터(마스코트의 픽셀 언어와 통일).
- 마우스를 올리면 5시간 한도 리셋 시각을 툴팁으로 표시.
- 25% 구간을 넘길 때 한국어 음성으로 안내.
- 우클릭: 지금 새로고침 / 설정 / 위치 초기화 / 종료. 드래그로 이동.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from tkinter import colorchooser

from .config import Config, load as load_config, save as save_config
from .provider import UsageProvider, UsageSnapshot

log = logging.getLogger(__name__)

# 모서리 투명 처리에 쓰는 매직 컬러(실제 UI에 쓰지 않는 색).
TRANSPARENT = "#010203"

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

PLAN_LABELS = [("pro", "Pro"), ("max5x", "Max 5x"), ("max20x", "Max 20x")]

CARD_H = 54
SEGMENTS = 10


class MonitorApp:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.provider = UsageProvider(cfg)
        self._alive = True
        self._last_snap: "UsageSnapshot | None" = None
        self._settings_win: "tk.Toplevel | None" = None
        self._tip: "tk.Toplevel | None" = None
        self._voice_bucket: "int | None" = None

        self.root = tk.Tk()
        self.root.title("Claude 5h Usage")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        self._set_opacity()

        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="지금 새로고침", command=self._refresh_now)
        self.menu.add_command(label="설정…", command=self.open_settings)
        self.menu.add_command(label="위치 초기화", command=self._reset_position)
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=self._quit)

        self._drag: dict = {}
        self._bind_events()
        self._render(None)
        self._place_window()
        self.root.after(200, self._schedule_poll)

    # ---------- 렌더 ----------
    def _set_opacity(self) -> None:
        try:
            self.root.attributes("-alpha", self.cfg.opacity)
        except tk.TclError:
            pass

    def _threshold_color(self, pct: float) -> str:
        if pct >= self.cfg.danger_percent:
            return self.cfg.color_danger
        if pct >= self.cfg.warn_percent:
            return self.cfg.color_warn
        return self.cfg.color_normal

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return canvas.create_polygon(pts, smooth=True, **kw)

    def _draw_mascot(self, canvas, ox, oy, cell) -> None:
        for r, row in enumerate(CLAUDE_MATRIX):
            for c, val in enumerate(row):
                if not val:
                    continue
                color = "#1a1714" if val == 2 else self.cfg.icon_color
                x0, y0 = ox + c * cell, oy + r * cell
                canvas.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill=color, outline=color)

    def _render(self, snap: "UsageSnapshot | None") -> None:
        cfg = self.cfg
        c = self.canvas
        c.delete("all")

        num_font = tkfont.Font(family=cfg.num_font_family, size=cfg.font_size, weight="bold")
        label_font = tkfont.Font(family=cfg.font_family, size=max(8, cfg.font_size - 6))

        pct = None if snap is None else snap.percent
        if pct is None:
            num_text, color = "--", cfg.color_dim
        else:
            prefix = "~" if snap.source == "estimate" else ""
            num_text, color = f"{prefix}{int(round(pct))}%", self._threshold_color(pct)
        disp_num = num_text + (" ·" if (snap and snap.stale) else "")
        label_text = "5시간 사용량"

        pad = 14
        x = pad
        cell = 0
        mascot_x = mascot_y = 0
        if cfg.show_icon:
            mrows, mcols = len(CLAUDE_MATRIX), len(CLAUDE_MATRIX[0])
            cell = max(2, round(cfg.icon_size / mrows))
            mascot_x, mascot_y = pad, (CARD_H - mrows * cell) // 2
            x = pad + mcols * cell + 12
        text_x = x

        label_w = label_font.measure(label_text)
        num_w = num_font.measure(disp_num)
        seg_w, seg_h, seg_gap = 5, 9, 3
        meter_w = SEGMENTS * seg_w + (SEGMENTS - 1) * seg_gap
        meter_x = text_x + num_w + 12
        right_w = max(label_w, num_w + 12 + meter_w)
        width = text_x + right_w + pad

        c.config(width=width, height=CARD_H)
        self._round_rect(c, 1, 1, width - 1, CARD_H - 1, cfg.corner_radius,
                         fill=cfg.color_bg, outline=cfg.color_border, width=1)
        if cfg.show_icon:
            self._draw_mascot(c, mascot_x, mascot_y, cell)

        label_y, num_y = 17, 37
        c.create_text(text_x, label_y, text=label_text, anchor="w",
                      fill=cfg.color_dim, font=label_font)
        c.create_text(text_x, num_y, text=disp_num, anchor="w", fill=color, font=num_font)

        filled = 0 if pct is None else max(0, min(SEGMENTS, round(pct * SEGMENTS / 100)))
        sy = num_y - seg_h // 2
        for i in range(SEGMENTS):
            sx = meter_x + i * (seg_w + seg_gap)
            seg_color = color if i < filled else cfg.color_track
            c.create_rectangle(sx, sy, sx + seg_w, sy + seg_h, fill=seg_color, outline=seg_color)

    def apply_config(self) -> None:
        """설정 변경을 실행 중 UI에 즉시 반영하고 저장."""
        self.root.configure(bg=TRANSPARENT)
        self._set_opacity()
        self._render(self._last_snap)
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
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_menu)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _on_press(self, event) -> None:
        self._hide_tip()
        self._drag = {"x": event.x_root, "y": event.y_root,
                      "ox": self.root.winfo_x(), "oy": self.root.winfo_y(), "moved": False}

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
        self._hide_tip()
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

    # ---------- 리셋 시각 툴팁 ----------
    def _reset_text(self) -> "str | None":
        snap = self._last_snap
        if snap is None or snap.resets_at is None:
            return None
        local = snap.resets_at.astimezone()
        remain = snap.resets_at - datetime.now(timezone.utc)
        mins = max(0, int(remain.total_seconds() // 60))
        h, m = divmod(mins, 60)
        ampm = "오전" if local.hour < 12 else "오후"
        hh = local.hour % 12 or 12
        when = f"{ampm} {hh}시 {local.minute:02d}분"
        left = f"{h}시간 {m}분 남음" if h else f"{m}분 남음"
        prefix = "예상 " if snap.source == "estimate" else ""
        return f"{prefix}리셋 {when} · {left}"

    def _on_enter(self, event) -> None:
        text = self._reset_text()
        if not text:
            return
        self._hide_tip()
        tip = tk.Toplevel(self.root)
        self._tip = tip
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        try:
            tip.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        tk.Label(tip, text=text, bg="#15130f", fg="#e8e1d4",
                 font=(self.cfg.font_family, 9), padx=9, pady=5).pack()
        tip.update_idletasks()
        x = self.root.winfo_x()
        y = self.root.winfo_y() + self.root.winfo_height() + 4
        tip.geometry(f"+{x}+{y}")

    def _on_leave(self, event) -> None:
        self._hide_tip()

    def _hide_tip(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    # ---------- 음성 알림 ----------
    def _maybe_voice(self, pct: float) -> None:
        if not self.cfg.voice_enabled:
            return
        bucket = min(4, int(pct // 25))
        if self._voice_bucket is None or bucket < self._voice_bucket:
            self._voice_bucket = bucket  # 최초/리셋은 무음으로 재무장
            return
        if bucket > self._voice_bucket:
            self._voice_bucket = bucket
            from .voice import speak
            threading.Thread(target=speak, args=(f"{bucket * 25}퍼센트 소진했습니다",),
                             daemon=True).start()

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
        if snap.percent is not None:
            self._maybe_voice(snap.percent)
        self._render(snap)

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

        self.voice_var = tk.BooleanVar(value=self.cfg.voice_enabled)
        tk.Checkbutton(win, text="음성 알림 (25%마다)", variable=self.voice_var).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1

        self.font_size_var = tk.IntVar(value=self.cfg.font_size)
        row = self._spin(win, "숫자 크기", self.font_size_var, 10, 28, row)
        self.icon_size_var = tk.IntVar(value=self.cfg.icon_size)
        row = self._spin(win, "아이콘 크기", self.icon_size_var, 14, 48, row)

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
        cfg.voice_enabled = bool(self.voice_var.get())
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
