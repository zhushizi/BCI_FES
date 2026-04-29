from __future__ import annotations

import logging
from typing import Any, Optional

from application.session_app import SessionApp
from service.business.training.training_sub_service import TrainingSubService


class TrainingSubApp:
    """
    训练副屏应用层：编排 UI 与范式服务，并把范式反馈写入患者绑定缓存。
    """

    def __init__(self, session_app: SessionApp, training_service: TrainingSubService):
        self.session_app = session_app
        self.service = training_service
        self.logger = logging.getLogger(__name__)
        self._current_patient_id: Optional[str] = None
        self._on_start_decoding = None
        self._on_stage_rest = None

        self.service.set_on_paradigm_params(self._on_paradigm_params)

    def set_current_patient(self, patient_id: str) -> None:
        self._current_patient_id = str(patient_id or "").strip() or None

    def connect(self) -> None:
        self.service.connect()

    def disconnect(self) -> None:
        self.service.disconnect()

    def start(self) -> None:
        if not self._current_patient_id:
            return
        self.service.start_paradigm(self._current_patient_id)

    def stop(self) -> None:
        self.service.stop_paradigm()

    def set_on_start_decoding(self, handler) -> None:
        self._on_start_decoding = handler

    def set_on_stage_rest(self, handler) -> None:
        """主控收到 paradigm.Stage params.stage=rest 时调用（暂停倒计时）。"""
        self._on_stage_rest = handler

    def _on_paradigm_params(self, params: dict[str, Any]) -> None:
        pid = self._current_patient_id
        try:
            method = str(params.get("method", "") or "")
            if method == "paradigm.Stage":
                inner = params.get("params") or {}
                if str(inner.get("stage") or "").strip().lower() == "rest":
                    if self._on_stage_rest:
                        self._on_stage_rest()
            elif method == "paradigm.start_decoding":
                if pid:
                    self.session_app.record_train_start_time()
                if self._on_start_decoding:
                    self._on_start_decoding()
                if pid:
                    self.session_app.save_paradigm_params(pid, params)
            elif pid:
                self.session_app.save_paradigm_params(pid, params)
        except Exception:
            pass

