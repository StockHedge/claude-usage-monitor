"""tkinter 팝업 UI + 설정 창.

디자인: "픽셀 인스트루먼트 HUD"
- 따뜻한 다크 라운드 카드(모서리는 Windows -transparentcolor로 실제 둥글게).
- 왼쪽에 Claude 픽셀 캐릭터(브랜드), 오른쪽에 작은 '5시간 사용량' 라벨 + 큰 퍼센트 숫자.
- 시그니처: 픽셀 세그먼트 미터(마스코트의 픽셀 언어와 통일).
- 오른쪽-아래 모서리를 드래그하면 전체 배율을 조절(최소~최대 제한).
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

TRANSPARENT = "#010203"  # 모서리 투명 처리용 매직 컬러

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

SEGMENTS = 10
SCALE_MIN = 0.75
SCALE_MAX = 2.2
GRIP = 16  # 오른쪽-아래 리사이즈 핸들 영역(px)


class MonitorApp:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.provider = UsageProvider(cfg)
        self._alive = True
        self._last_snap: "UsageSnapshot | None" = None
        self._settings_win: "tk.Toplevel | None" = None
        self._tip: "tk.Toplevel | None" = None
        self._voice_bucket: "int | None" = None
        self._mode: "str | None" = None
        self._w = self._h = 0

        self.root = tk.Tk()
        self.root.title("Claude 5h Usage")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=cfg.color_bg)
        self._set_opacity()

        # 주의: Windows에서 -transparentcolor + -alpha 동시 사용은 창을 비가시로 만든다.
        # 신뢰성을 위해 alpha(투명도)만 쓰고 카드는 solid로 그린다.
        self.canvas = tk.Canvas(self.root, bg=cfg.color_bg, highlightthickness=0, bd=0)
        self.canvas.pack()

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="지금 새로고침", command=self._refresh_now)
        self.menu.add_command(label="설정…", command=self.open_settings)
        self.menu.add_command(label="위치 초기화", command=self._reset_position)
        self.menu.add_command(label="크기 초기화", command=self._reset_scale)
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=self._quit)

        self._drag: dict = {}
        self._rs: dict = {}
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

    def _scale(self) -> float:
        return max(SCALE_MIN, min(SCALE_MAX, self.cfg.ui_scale))

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
        s = self._scale()

        num_font = tkfont.Font(family=cfg.num_font_family, size=max(9, round(cfg.font_size * s)),
                               weight="bold")
        label_font = tkfont.Font(family=cfg.font_family, size=max(7, round((cfg.font_size - 6) * s)))

        pct = None if snap is None else snap.percent
        if pct is None:
            num_text, color = "--", cfg.color_dim
        else:
            prefix = "~" if snap.source == "estimate" else ""
            num_text, color = f"{prefix}{int(round(pct))}%", self._threshold_color(pct)
        disp_num = num_text + (" ·" if (snap and snap.stale) else "")
        label_text = "5시간 사용량"

        pad = round(14 * s)
        gap = round(12 * s)
        H = round(54 * s)
        mrows, mcols = len(CLAUDE_MATRIX), len(CLAUDE_MATRIX[0])
        cell = max(2, round(cfg.icon_size / mrows * s))

        x = pad
        mascot_x = mascot_y = 0
        if cfg.show_icon:
            mascot_x, mascot_y = pad, (H - mrows * cell) // 2
            x = pad + mcols * cell + gap
        text_x = x

        label_w = label_font.measure(label_text)
        num_w = num_font.measure(disp_num)
        seg_w, seg_h, seg_gap = max(3, round(5 * s)), max(5, round(9 * s)), max(2, round(3 * s))
        meter_w = SEGMENTS * seg_w + (SEGMENTS - 1) * seg_gap
        meter_x = text_x + num_w + gap
        right_w = max(label_w, num_w + gap + meter_w)
        width = text_x + right_w + pad

        self._w, self._h = width, H
        c.config(width=width, height=H, bg=cfg.color_bg)
        self._round_rect(c, 1, 1, width - 1, H - 1, round(cfg.corner_radius * s),
                         fill=cfg.color_bg, outline=cfg.color_border, width=1)
        if cfg.show_icon:
            self._draw_mascot(c, mascot_x, mascot_y, cell)

        label_y, num_y = round(H * 0.30), round(H * 0.66)
        c.create_text(text_x, label_y, text=label_text, anchor="w",
                      fill=cfg.color_dim, font=label_font)
        c.create_text(text_x, num_y, text=disp_num, anchor="w", fill=color, font=num_font)

        filled = 0 if pct is None else max(0, min(SEGMENTS, round(pct * SEGMENTS / 100)))
        sy = num_y - seg_h // 2
        for i in range(SEGMENTS):
            sx = meter_x + i * (seg_w + seg_gap)
            seg_color = color if i < filled else cfg.color_track
            c.create_rectangle(sx, sy, sx + seg_w, sy + seg_h, fill=seg_color, outline=seg_color)

        # 오른쪽-아래 리사이즈 그립
        for off in (4, 8, 12):
            c.create_line(width - off, H - 3, width - 3, H - off, fill=cfg.color_dim, width=1)

    def apply_config(self) -> None:
        self.root.configure(bg=self.cfg.color_bg)
        self._set_opacity()
        self._render(self._last_snap)
        save_config(self.cfg)

    # ---------- 위치/드래그/리사이즈 ----------
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
        cv = self.canvas
        cv.bind("<Button-1>", self._on_press)
        cv.bind("<B1-Motion>", self._on_drag)
        cv.bind("<ButtonRelease-1>", self._on_release)
        cv.bind("<Button-3>", self._on_menu)
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Enter>", self._on_enter)
        cv.bind("<Leave>", self._on_leave)

    def _in_grip(self, event) -> bool:
        return event.x >= self._w - GRIP and event.y >= self._h - GRIP

    def _on_motion(self, event) -> None:
        self.canvas.config(cursor="size_nw_se" if self._in_grip(event) else "")

    def _on_press(self, event) -> None:
        self._hide_tip()
        if self._in_grip(event):
            self._mode = "resize"
            self._rs = {"x": event.x_root, "y": event.y_root, "scale": self._scale()}
        else:
            self._mode = "move"
            self._drag = {"x": event.x_root, "y": event.y_root,
                          "ox": self.root.winfo_x(), "oy": self.root.winfo_y(), "moved": False}

    def _on_drag(self, event) -> None:
        if self._mode == "resize":
            delta = ((event.x_root - self._rs["x"]) + (event.y_root - self._rs["y"])) / 2.0
            self.cfg.ui_scale = max(SCALE_MIN, min(SCALE_MAX, self._rs["scale"] + delta / 160.0))
            self._render(self._last_snap)
        elif self._mode == "move":
            dx = event.x_root - self._drag["x"]
            dy = event.y_root - self._drag["y"]
            if abs(dx) > 2 or abs(dy) > 2:
                self._drag["moved"] = True
            self.root.geometry(f"+{self._drag['ox'] + dx}+{self._drag['oy'] + dy}")

    def _on_release(self, event) -> None:
        if self._mode == "resize":
            save_config(self.cfg)
        elif self._mode == "move" and self._drag.get("moved"):
            self.cfg.window_x = self.root.winfo_x()
            self.cfg.window_y = self.root.winfo_y()
            save_config(self.cfg)
        self._mode = None

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

    def _reset_scale(self) -> None:
        self.cfg.ui_scale = 1.0
        self._render(self._last_snap)
        save_config(self.cfg)

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
            tip.attributes("-alpha", 0.97)
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

    # ---------- 음성 ----------
    def _maybe_voice(self, pct: float) -> None:
        if not self.cfg.voice_enabled:
            return
        bucket = min(4, int(pct // 25))
        if self._voice_bucket is None or bucket < self._voice_bucket:
            self._voice_bucket = bucket
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

    def open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        SettingsWindow(self)

    def run(self) -> None:
        self.root.mainloop()


# 설정 창 팔레트
S_BG = "#201d19"
S_FG = "#ece5d8"
S_DIM = "#9a9082"
S_FIELD = "#332f29"
S_ACCENT = "#d97757"
S_LINE = "#3a352e"


class SettingsWindow:
    """다크·섹션·스크롤 설정 창. 저장 시 MonitorApp.apply_config로 즉시 반영."""

    COLOR_FIELDS = [
        ("color_bg", "배경"),
        ("color_normal", "정상"),
        ("color_warn", "주의"),
        ("color_danger", "위험"),
        ("icon_color", "아이콘"),
    ]

    def __init__(self, app: MonitorApp):
        self.app = app
        self.cfg = app.cfg
        win = tk.Toplevel(app.root)
        app._settings_win = win
        self.win = win
        win.title("설정")
        win.configure(bg=S_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._close)

        tk.Label(win, text="설정", bg=S_BG, fg=S_FG,
                 font=("Malgun Gothic", 13, "bold")).pack(anchor="w", padx=16, pady=(12, 6))

        # 스크롤 컨테이너(내용이 길어도 잘리지 않게)
        container = tk.Frame(win, bg=S_BG)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=S_BG, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=S_BG)
        self.body.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._canvas = canvas

        self._colors = {key: tk.StringVar(value=getattr(self.cfg, key))
                        for key, _ in self.COLOR_FIELDS}

        self._build()

        # 버튼 바(항상 보이게 하단 고정)
        bar = tk.Frame(win, bg=S_BG)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=S_LINE, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=S_BG)
        inner.pack(anchor="e", padx=16, pady=10)
        self._btn(inner, "저장", self._save, accent=True).pack(side="left", padx=4)
        self._btn(inner, "취소", self._close, accent=False).pack(side="left", padx=4)

        self._size_and_center()
        win.transient(app.root)
        win.lift()

    # ---- 스타일 헬퍼 ----
    def _section(self, title: str) -> None:
        tk.Label(self.body, text=title, bg=S_BG, fg=S_ACCENT,
                 font=("Malgun Gothic", 9, "bold")).grid(
            row=self._row, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 2))
        self._row += 1

    def _cap(self, text: str) -> tk.Label:
        lbl = tk.Label(self.body, text=text, bg=S_BG, fg=S_FG, font=("Malgun Gothic", 9))
        lbl.grid(row=self._row, column=0, sticky="w", padx=(18, 8), pady=3)
        return lbl

    def _check(self, text: str, var: tk.BooleanVar) -> None:
        tk.Checkbutton(self.body, text=text, variable=var, bg=S_BG, fg=S_FG,
                       selectcolor=S_FIELD, activebackground=S_BG, activeforeground=S_FG,
                       highlightthickness=0, bd=0, font=("Malgun Gothic", 9)).grid(
            row=self._row, column=0, columnspan=2, sticky="w", padx=16, pady=2)
        self._row += 1

    def _spin(self, text, var, lo, hi) -> None:
        self._cap(text)
        tk.Spinbox(self.body, from_=lo, to=hi, textvariable=var, width=7,
                   bg=S_FIELD, fg=S_FG, buttonbackground=S_FIELD, relief="flat",
                   highlightthickness=0, bd=2, insertbackground=S_FG,
                   font=("Consolas", 9)).grid(row=self._row, column=1, sticky="w", padx=(0, 16))
        self._row += 1

    def _scale(self, text, var, lo, hi, res) -> None:
        self._cap(text)
        tk.Scale(self.body, from_=lo, to=hi, resolution=res, orient="horizontal",
                 variable=var, bg=S_BG, fg=S_DIM, troughcolor=S_FIELD, highlightthickness=0,
                 bd=0, activebackground=S_ACCENT, length=120,
                 font=("Consolas", 8)).grid(row=self._row, column=1, sticky="w", padx=(0, 16))
        self._row += 1

    def _option(self, text, var, options) -> None:
        self._cap(text)
        om = tk.OptionMenu(self.body, var, *options)
        om.config(bg=S_FIELD, fg=S_FG, activebackground=S_ACCENT, activeforeground="#fff",
                  highlightthickness=0, bd=0, font=("Malgun Gothic", 9), width=8)
        om["menu"].config(bg=S_FIELD, fg=S_FG, activebackground=S_ACCENT, activeforeground="#fff")
        om.grid(row=self._row, column=1, sticky="w", padx=(0, 16))
        self._row += 1

    def _color_row(self, text, key) -> None:
        self._cap(text)
        holder = tk.Frame(self.body, bg=S_BG)
        holder.grid(row=self._row, column=1, sticky="w", padx=(0, 16))
        swatch = tk.Label(holder, width=3, bg=self._colors[key].get(), relief="flat", bd=0)
        swatch.pack(side="left", padx=(0, 6))

        def pick():
            chosen = colorchooser.askcolor(color=self._colors[key].get(), parent=self.win)
            if chosen and chosen[1]:
                self._colors[key].set(chosen[1])
                swatch.config(bg=chosen[1])

        self._btn(holder, "선택", pick, accent=False, small=True).pack(side="left")
        self._row += 1

    def _btn(self, parent, text, cmd, accent=True, small=False):
        return tk.Button(parent, text=text, command=cmd, bd=0, cursor="hand2",
                         bg=(S_ACCENT if accent else S_FIELD),
                         fg=("#20180f" if accent else S_FG),
                         activebackground=(S_ACCENT if accent else S_LINE),
                         activeforeground=("#20180f" if accent else S_FG),
                         font=("Malgun Gothic", 9, "bold" if accent else "normal"),
                         padx=(8 if small else 14), pady=(2 if small else 4))

    # ---- 본문 구성 ----
    def _build(self) -> None:
        self.body.columnconfigure(1, weight=1)
        self._row = 0

        self._section("표시")
        self.plan_var = tk.StringVar(value=self._plan_label(self.cfg.plan))
        self._option("요금제", self.plan_var, [lbl for _, lbl in PLAN_LABELS])
        self.show_icon_var = tk.BooleanVar(value=self.cfg.show_icon)
        self._check("Claude 캐릭터 아이콘 표시", self.show_icon_var)
        self.scale_var = tk.DoubleVar(value=round(self.cfg.ui_scale, 2))
        self._scale("전체 크기(배율)", self.scale_var, SCALE_MIN, SCALE_MAX, 0.05)
        self.font_size_var = tk.IntVar(value=self.cfg.font_size)
        self._spin("숫자 크기", self.font_size_var, 10, 28)
        self.icon_size_var = tk.IntVar(value=self.cfg.icon_size)
        self._spin("아이콘 크기", self.icon_size_var, 14, 48)
        self.opacity_var = tk.DoubleVar(value=self.cfg.opacity)
        self._scale("투명도", self.opacity_var, 0.4, 1.0, 0.02)

        self._section("동작")
        self.voice_var = tk.BooleanVar(value=self.cfg.voice_enabled)
        self._check("음성 알림 (25%마다)", self.voice_var)
        self.warn_var = tk.IntVar(value=int(self.cfg.warn_percent))
        self._spin("주의 임계값 %", self.warn_var, 0, 100)
        self.danger_var = tk.IntVar(value=int(self.cfg.danger_percent))
        self._spin("위험 임계값 %", self.danger_var, 0, 100)
        self.poll_var = tk.IntVar(value=self.cfg.poll_interval_sec)
        self._spin("갱신 주기(초)", self.poll_var, 30, 600)

        self._section("색상")
        for key, text in self.COLOR_FIELDS:
            self._color_row(text, key)

    def _size_and_center(self) -> None:
        self.win.update_idletasks()
        req_w = max(self.body.winfo_reqwidth() + 24, 300)
        content_h = self.body.winfo_reqheight() + 120  # 헤더+버튼바 여유
        screen_h = self.win.winfo_screenheight()
        win_h = min(content_h, int(screen_h * 0.85))
        x = (self.win.winfo_screenwidth() - req_w) // 2
        y = (screen_h - win_h) // 2
        self.win.geometry(f"{req_w}x{win_h}+{x}+{max(0, y)}")

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
        try:
            self._canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self.app._settings_win = None
        self.win.destroy()

    def _save(self) -> None:
        cfg = self.cfg
        cfg.apply_plan(self._plan_key(self.plan_var.get()))
        cfg.show_icon = bool(self.show_icon_var.get())
        cfg.voice_enabled = bool(self.voice_var.get())
        cfg.ui_scale = float(self.scale_var.get())
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
