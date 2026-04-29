from __future__ import annotations

import logging
from typing import Optional, Tuple

from application.session_app import SessionApp
from application.training_main_app import TrainingMainApp


class TrainingFlowApp:
    """训练流程应用层：编排暂停/开始/停止与 WS 通知。"""

    def __init__(self, session_app: SessionApp, training_app: TrainingMainApp, logger: Optional[logging.Logger] = None):
        self._session_app = session_app
        self._training_app = training_app
        self._logger = logger or logging.getLogger(__name__)

    def check_pause_allowed(self, pretrain_full_completed: bool) -> Tuple[bool, str]:
        session_data = None
        try:
            session_data = self._session_app.get_current_patient_treat_session()
        except Exception:
            session_data = None
        paradigm = str((session_data or {}).get("Paradigm", "") or "").strip().upper()
        if paradigm in ("SSMVEP", "MI") and not pretrain_full_completed:
            return False, "预训练未完成无法暂停"
        return True, ""

    def notify_pause(self) -> None:
        self._send_notification("main.stop_session")

    def notify_start(self) -> None:
        self._send_notification("paradigm.start_decoding")

    def notify_shut_down(self) -> None:
        self._send_notification("paradigm.shut_down")

    def notify_stop_and_shutdown(self) -> None:
        self._send_notification("main.stop_session")
        self._send_notification("paradigm.shut_down")

    def _send_notification(self, target: str) -> None:
        try:
            self._training_app.send_notification(
                "main.tigger",
                {"tigger_target": target},
            )
        except Exception as exc:
            self._logger.debug("发送通知失败: %s", exc)
