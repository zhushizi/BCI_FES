from __future__ import annotations

import logging
from typing import Any, Optional

from application.session_app import SessionApp
from service.business.storage.erds_storage_service import ErdsStorageService
from service.business.training.training_main_service import TrainingMainService


class TrainingMainApp:
    """
    训练主屏应用层：编排 UI 与解码器服务，并把解码器反馈写入患者绑定缓存。
    """

    def __init__(
        self,
        session_app: SessionApp,
        training_service: TrainingMainService,
        erds_storage: Optional[ErdsStorageService] = None,
    ):
        self.session_app = session_app
        self.service = training_service
        self.erds_storage = erds_storage
        self.logger = logging.getLogger(__name__)
        self._current_patient_id: Optional[str] = None
        self._on_intent_result = None
        self._on_pretrain_full_completed: Optional[object] = None  # Callable[[], None]

        # 注册解码器消息回调（框架阶段：按 dict 直接缓存）
        self.service.set_on_decoder_params(self._on_decoder_params)

    def set_current_patient(self, patient_id: str) -> None:
        self._current_patient_id = str(patient_id or "").strip() or None

    def connect(self) -> None:
        self.service.connect()

    def disconnect(self) -> None:
        self.service.disconnect()

    def start(self) -> None:
        if not self._current_patient_id:
            return
        self.service.start_training(self._current_patient_id)

    def stop(self) -> None:
        self.service.stop_training()

    def send_notification(self, method: str, params: dict) -> None:
        self.service.send_notification(method, params)

    def set_wave_callback(self, handler) -> None:
        """注册 EEG 波形回调（用于 UI 展示）。"""
        if handler:
            self.service.set_on_eeg_frame(handler)

    def set_intent_callback(self, handler) -> None:
        """注册 intent_result 回调（用于 UI 展示）。"""
        self._on_intent_result = handler

    def set_on_pretrain_full_completed(self, handler) -> None:
        """注册 decoder.Inform pretrain=pretrain_full_completed 回调（SSMVEP/MI 训练完成后可暂停）。"""
        self._on_pretrain_full_completed = handler

    def _on_decoder_params(self, params: dict[str, Any]) -> None:
        pid = self._current_patient_id
        if not pid:
            return
        try:
            method = str(params.get("method", "") or "")
            msg_params = params.get("params") or {}
            self.session_app.save_decoder_params(pid, params)
            if method == "decoder.BCIReport":
                self._handle_bci_report(pid, msg_params)
            elif method == "decoder.intent_result":
                self._handle_intent_result(msg_params)
            elif method == "decoder.Inform":
                self._handle_pretrain_info(msg_params)
        except Exception:
            # 框架阶段：不阻断 UI 流程
            pass

    def _handle_bci_report(self, patient_id: str, msg_params: dict[str, Any]) -> None:
        self.session_app.save_train_result(patient_id, msg_params)
        try:
            self.logger.info("收到 decoder.BCIReport: patient_id=%s", patient_id)
            self.logger.info("decoder.BCIReport ERDs: %s", msg_params.get("ERDs"))
            self._save_erds_image(msg_params.get("ERDs"), patient_id)
        except Exception:
            pass

    def _handle_intent_result(self, msg_params: dict[str, Any]) -> None:
        if not self._on_intent_result:
            return
        payload = {
            "trial_index": msg_params.get("trial_index"),
            "t_complete_r": msg_params.get("t_complete_r"),
            "reaction_time": msg_params.get("reaction_time"),
        }
        self._on_intent_result(payload)

    def _handle_pretrain_info(self, msg_params: dict[str, Any]) -> None:
        if msg_params.get("pretrain") != "pretrain_full_completed":
            return
        if callable(self._on_pretrain_full_completed):
            try:
                self._on_pretrain_full_completed()
            except Exception:
                pass

    def _save_erds_image(self, erds_base64: Any, patient_id: str) -> None:
        if not erds_base64 or not self.session_app or not self.erds_storage:
            return
        try:
            session_id = self.session_app.get_current_session_id()
            relative_path = self.erds_storage.save_erds_image(erds_base64, patient_id, session_id)
            if relative_path:
                self.session_app.update_erds_path(relative_path)
                self.logger.info("ERDs 图片已保存: %s", relative_path)
        except Exception:
            self.logger.exception("保存 ERDs 图片失败")

