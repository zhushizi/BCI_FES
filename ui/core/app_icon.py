"""
应用/window 图标：开发目录与 PyInstaller 打包后路径解析。

任务栏图标依赖 Qt 的 setWindowIcon；仅设置 .exe 的 PyInstaller --icon 往往不够。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ICON_NAMES = ("icon_BCI.ico", "icon_BCI.png")


def _project_root_from_this_file() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_app_icon_path() -> Optional[Path]:
    """优先.ico，其次.png；打包后从 sys._MEIPASS 查找，否则从源码树 ui/pic 查找。"""
    bases: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(Path(meipass))
    bases.append(_project_root_from_this_file())

    for base in bases:
        for name in _ICON_NAMES:
            p = base / "ui" / "pic" / name
            if p.is_file():
                return p
    return None


def apply_application_icon(app: object) -> None:
    """对 QApplication 设置默认窗口图标（影响任务栏等）。"""
    p = resolve_app_icon_path()
    if not p:
        return
    try:
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(p)))
    except Exception:
        pass


def apply_window_icon(widget: object) -> None:
    """对顶层 QWidget / QDialog 设置图标。"""
    p = resolve_app_icon_path()
    if not p:
        return
    try:
        from PySide6.QtGui import QIcon

        setter = getattr(widget, "setWindowIcon", None)
        if callable(setter):
            setter(QIcon(str(p)))
    except Exception:
        pass


__all__ = ["resolve_app_icon_path", "apply_application_icon", "apply_window_icon"]
