"""최초 실행 설정 GUI.

요금제 선택 + 자동 시작 등록 후 팝업을 실행한다. install.bat이 이 화면을 호출한다.
"""
from __future__ import annotations

import logging
import subprocess
import tkinter as tk
from tkinter import messagebox

from . import autostart
from .config import load as load_config, save as save_config
from .credentials import read_credentials
from .logsetup import setup_logging
from .ui import PLAN_LABELS

log = logging.getLogger(__name__)

DETACHED_PROCESS = 0x00000008


def _launch_popup() -> None:
    """설정 완료 후 팝업을 콘솔 없이 분리 실행."""
    try:
        pythonw = autostart._pythonw()
        target = autostart._run_target()
        subprocess.Popen([str(pythonw), str(target)], creationflags=DETACHED_PROCESS)
    except Exception:
        log.exception("팝업 실행 실패")


def _label_for(key: str) -> str:
    for k, lbl in PLAN_LABELS:
        if k == key:
            return lbl
    return "Max 5x"


def _key_for(label: str) -> str:
    for k, lbl in PLAN_LABELS:
        if lbl == label:
            return k
    return "max5x"


def run_setup() -> None:
    setup_logging()
    cfg = load_config()

    win = tk.Tk()
    win.title("Claude 사용량 모니터 · 설정")
    win.resizable(False, False)
    win.configure(padx=18, pady=16)

    tk.Label(win, text="Claude 5시간 사용량 모니터",
             font=("Malgun Gothic", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 12))

    tk.Label(win, text="사용 중인 요금제").grid(row=1, column=0, sticky="w", pady=4)
    plan_var = tk.StringVar(value=_label_for(cfg.plan))
    tk.OptionMenu(win, plan_var, *[lbl for _, lbl in PLAN_LABELS]).grid(
        row=1, column=1, sticky="ew", pady=4)

    autostart_var = tk.BooleanVar(value=True)
    tk.Checkbutton(win, text="Windows 로그인 시 자동 시작", variable=autostart_var).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=4)

    creds = read_credentials()
    if creds:
        status_text = "Claude Code 로그인 감지됨 — 라이브 정확값을 표시합니다."
        status_color = "#2e7d32"
    else:
        status_text = ("Claude Code 자격증명을 찾지 못했습니다. 추정 모드로 동작하며, "
                       "Claude Code에 로그인하면 자동으로 정확값으로 전환됩니다.")
        status_color = "#b26a00"
    tk.Label(win, text=status_text, fg=status_color, wraplength=300,
             justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 12))

    def submit():
        cfg.apply_plan(_key_for(plan_var.get()))
        save_config(cfg)
        if autostart_var.get():
            try:
                autostart.install()
            except Exception:
                log.exception("자동 시작 등록 실패")
                messagebox.showwarning(
                    "자동 시작", "자동 시작 등록에 실패했습니다. 수동 실행(start.bat)은 가능합니다.")
        win.destroy()
        _launch_popup()

    tk.Button(win, text="설치하고 시작", width=20, command=submit).grid(
        row=4, column=0, columnspan=2, pady=(4, 0))

    win.columnconfigure(1, weight=1)
    try:
        win.eval("tk::PlaceWindow . center")
    except tk.TclError:
        pass
    win.attributes("-topmost", True)
    win.lift()
    win.focus_force()
    win.mainloop()
