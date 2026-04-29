from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from application.patient_app import PatientApp
from application.training_sub_app import TrainingSubApp
from ui.main_window.sub_window import SubWindow
from ui.core.utils import safe_call

DEFAULT_PARADIGM_EXE = r"C:\Users\24114\Desktop\ParadigmSSMVEP\ParadigmOne.exe"


class TrainingSubController:
    """
    训练模块副屏（sub_window.ui 的 tabWidget index=1 / tab_2）。

    框架阶段：
    - 只负责副屏 tab 切换与把患者 id 传给 TrainingSubApp
    - 范式播放的具体 UI 控件绑定后续再补
    """

    def __init__(
        self,
        sub_window: Optional[SubWindow] = None,
        patient_app: Optional[PatientApp] = None,
        training_app: Optional[TrainingSubApp] = None,
        paradigm_exe_path: Optional[str] = None,
        hide_console: bool = False,
    ):
        self.sub_window = sub_window
        self.patient_app = patient_app
        self.training_app = training_app
        self._logger = logging.getLogger(__name__)
        self._current_patient_id: Optional[str] = None
        self._paradigm_process: Optional[subprocess.Popen] = None
        self._hide_console = bool(hide_console)
        if paradigm_exe_path is None:
            self._paradigm_exe_path = DEFAULT_PARADIGM_EXE
        else:
            self._paradigm_exe_path = str(paradigm_exe_path).strip()

    def bind_signals(self) -> None:
        return

    def set_paradigm_exe_path(self, exe_path: Optional[str]) -> None:
        next_path = str(exe_path or "").strip()
        if not next_path:
            return
        self._paradigm_exe_path = next_path

    def set_current_patient(self, patient_id: Optional[str]) -> None:
        self._current_patient_id = str(patient_id or "").strip() or None
        if self.training_app:
            if self._current_patient_id:
                self.training_app.set_current_patient(self._current_patient_id)
            else:
                self.training_app.set_current_patient("")

    def show_paradigm_tab(self) -> None:
        """切到副屏范式播放页（index=1）。"""
        if self.sub_window:
            self.sub_window.switch_tab(1)

    def show_welcome_tab(self) -> None:
        if self.sub_window:
            self.sub_window.switch_tab(0)

    def start_paradigm_service(self, switch_tab: bool = True, show_screen: bool = True) -> bool:
        """
        启动范式模块（独立 exe）并切换到副屏。
        """
        exe_path = self._paradigm_exe_path
        args = ["1"]
        if not os.path.isfile(exe_path):
            self._logger.error("范式程序不存在: %s", exe_path)
            return False

        if self.sub_window:
            if show_screen:
                safe_call(self._logger, self.sub_window.show_on_screen, 2)
            if switch_tab:
                self.show_paradigm_tab()

        if self._paradigm_process and self._paradigm_process.poll() is None:
            return True

        try:
            creationflags = 0
            if os.name == "nt" and self._hide_console:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            self._paradigm_process = subprocess.Popen(
                [exe_path, *args],
                cwd=os.path.dirname(exe_path),
                creationflags=creationflags,
            )
            return True
        except Exception as exc:
            self._logger.error("启动范式程序失败: %s", exc)
            return False

