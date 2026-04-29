from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from application.patient_app import PatientApp
from service.business.session.session_service import SessionService


@dataclass
class PatientTreatParams:
    """
    患者治疗相关的“当前参数”（运行态缓存，部分会持久化）

    - left/right_grade: 0~99
    - left/right_scheme_idx: UI 下拉框索引（0/1）
    - left/right_freq_idx: UI 下拉框索引（0..9）
    """

    patient_id: str
    left_grade: int = 0
    right_grade: int = 0
    left_scheme_idx: int = 0
    right_scheme_idx: int = 0
    left_freq_idx: int = 0
    right_freq_idx: int = 0


@dataclass
class PatientSharedParams:
    """
    患者绑定的共享参数（仅内存缓存，不持久化）。

    - treat: 电刺激模块左右通道参数（沿用 PatientTreatParams）
    - decoder: 解码器反馈的脑电相关参数（dict 占位）
    - paradigm: 范式模块反馈的范式相关参数（dict 占位）
    """

    patient_id: str
    treat: Optional[PatientTreatParams] = None
    decoder: Optional[Dict[str, Any]] = None
    paradigm: Optional[Dict[str, Any]] = None


class SessionApp:
    """
    治疗会话应用层：
    - 负责组装患者信息
    - 创建/结束会话
    """

    def __init__(self, patient_app: PatientApp, session_service: SessionService):
        if patient_app is None:
            raise ValueError("patient_app 参数不能为 None")
        if session_service is None:
            raise ValueError("session_service 参数不能为 None")
        self.patient_app = patient_app
        self.service = session_service
        self.logger = logging.getLogger(__name__)
        self._current_session_id: Optional[int] = None
        self._current_patient_id: Optional[str] = None
        # 仅保留“当前患者”的参数（仅内存，程序退出后不恢复）
        self._current_treat_params: Optional[PatientTreatParams] = None
        self._current_decoder_params: Optional[Dict[str, Any]] = None
        self._current_paradigm_params: Optional[Dict[str, Any]] = None

    # --------- 治疗参数缓存（按患者，仅内存）---------
    def set_current_patient(self, patient_id: str) -> None:
        """
        切换当前患者。
        规则：一旦切换患者，上一位患者的所有参数立即清空，只保留当前患者参数。
        """
        patient_id = str(patient_id or "").strip()
        if not patient_id:
            self._current_patient_id = None
            self._current_treat_params = None
            self._current_decoder_params = None
            self._current_paradigm_params = None
            return
        if self._current_patient_id != patient_id:
            self._current_patient_id = patient_id
            self._current_treat_params = None
            self._current_decoder_params = None
            self._current_paradigm_params = None

    def load_treat_params(self, patient_id: str) -> Optional[PatientTreatParams]:
        patient_id = str(patient_id or "").strip()
        if not patient_id:
            return None
        if self._current_patient_id != patient_id:
            return None
        return self._current_treat_params

    def save_treat_params(self, params: PatientTreatParams) -> None:
        if not params or not str(params.patient_id).strip():
            return
        pid = str(params.patient_id).strip()
        # 保存即代表当前患者
        self._current_patient_id = pid
        self._current_treat_params = params
        if self._current_session_id:
            try:
                self.service.update_stim_params(
                    session_id=self._current_session_id,
                    patient_id=pid,
                    left_grade=params.left_grade,
                    right_grade=params.right_grade,
                    left_scheme_idx=params.left_scheme_idx,
                    right_scheme_idx=params.right_scheme_idx,
                    left_freq_idx=params.left_freq_idx,
                    right_freq_idx=params.right_freq_idx,
                )
            except Exception:
                pass

    # --------- 解码器/范式参数缓存（按患者，仅内存）---------
    def load_decoder_params(self, patient_id: str) -> Optional[Dict[str, Any]]:
        pid = str(patient_id or "").strip()
        if not pid:
            return None
        if self._current_patient_id != pid:
            return None
        return self._current_decoder_params

    def save_decoder_params(self, patient_id: str, params: Dict[str, Any]) -> None:
        pid = str(patient_id or "").strip()
        if not pid:
            return
        if self._current_patient_id != pid:
            # 写入即切换当前患者（与 save_treat_params 语义一致）
            self.set_current_patient(pid)
        self._current_decoder_params = dict(params or {})

    def save_train_result(self, patient_id: str, result: Dict[str, Any] | str) -> None:
        pid = str(patient_id or "").strip()
        if not pid or not self._current_session_id:
            return
        if self._current_patient_id != pid:
            self.set_current_patient(pid)
        payload = result
        if not isinstance(result, str):
            try:
                payload = json.dumps(result or {}, ensure_ascii=False)
            except Exception:
                payload = str(result)
        try:
            self.service.upsert_patient_treat_session(
                session_id=self._current_session_id,
                patient_id=pid,
                train_result=payload or "",
            )
        except Exception:
            pass

    def load_paradigm_params(self, patient_id: str) -> Optional[Dict[str, Any]]:
        pid = str(patient_id or "").strip()
        if not pid:
            return None
        if self._current_patient_id != pid:
            return None
        return self._current_paradigm_params

    def save_paradigm_params(self, patient_id: str, params: Dict[str, Any]) -> None:
        pid = str(patient_id or "").strip()
        if not pid:
            return
        if self._current_patient_id != pid:
            self.set_current_patient(pid)
        self._current_paradigm_params = dict(params or {})

    def load_shared_params(self, patient_id: str) -> Optional[PatientSharedParams]:
        pid = str(patient_id or "").strip()
        if not pid:
            return None
        if self._current_patient_id != pid:
            return None
        return PatientSharedParams(
            patient_id=pid,
            treat=self._current_treat_params,
            decoder=self._current_decoder_params,
            paradigm=self._current_paradigm_params,
        )

    def save_shared_params(self, params: PatientSharedParams) -> None:
        if not params or not str(params.patient_id).strip():
            return
        pid = str(params.patient_id).strip()
        self.set_current_patient(pid)
        if params.treat is not None:
            self._current_treat_params = params.treat
        if params.decoder is not None:
            self._current_decoder_params = dict(params.decoder or {})
        if params.paradigm is not None:
            self._current_paradigm_params = dict(params.paradigm or {})

    def start_session(
        self,
        patient_id: str,
        plan_name: str = "",
        body_part: str = "",
        paradigm: str = "",
        patient_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        pid = str(patient_id or "").strip()
        if not pid:
            return None

        if self._current_session_id:
            self.end_session("auto_end_on_new_start")

        patient = None
        try:
            patient = self.patient_app.get_patient_by_id(pid)
        except Exception:
            patient = None

        if not patient and patient_snapshot:
            patient = patient_snapshot

        patient = patient or {"PatientId": pid}

        session_id = self.service.start_session(
            patient_info=patient,
            plan_name=plan_name,
            body_part=body_part,
            paradigm=paradigm,
        )
        if session_id:
            self._current_session_id = int(session_id)
            self._current_patient_id = pid
        return session_id

    def end_session(self, reason: str = "manual_exit") -> bool:
        if not self._current_session_id:
            return False
        # 中途退出时把当前缓存参数落库
        try:
            if self._current_treat_params and self._current_patient_id:
                params = self._current_treat_params
                self.service.update_stim_params(
                    session_id=self._current_session_id,
                    patient_id=self._current_patient_id,
                    left_grade=params.left_grade,
                    right_grade=params.right_grade,
                    left_scheme_idx=params.left_scheme_idx,
                    right_scheme_idx=params.right_scheme_idx,
                    left_freq_idx=params.left_freq_idx,
                    right_freq_idx=params.right_freq_idx,
                )
        except Exception:
            pass
        ok = self.service.end_session(self._current_session_id, reason=reason)
        self._current_session_id = None
        self._current_patient_id = None
        return ok

    def has_active_session(self) -> bool:
        return bool(self._current_session_id)

    def get_current_session_id(self) -> Optional[int]:
        return self._current_session_id

    def get_current_patient_id(self) -> Optional[str]:
        return self._current_patient_id

    def record_train_start_time(self) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_train_start_time(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
            )
        except Exception:
            pass

    def update_average_reaction_time(self, average_reaction_time: float) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_average_reaction_time(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
                average_reaction_time=average_reaction_time,
            )
        except Exception:
            pass

    def update_average_reaction_time_curve(self, curve_path: str) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_average_reaction_time_curve(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
                curve_path=curve_path,
            )
        except Exception:
            pass

    def update_reaction_time_curve(self, curve_path: str) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_reaction_time_curve(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
                curve_path=curve_path,
            )
        except Exception:
            pass

    def update_erds_path(self, erds_path: str) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_erds_path(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
                erds_path=erds_path,
            )
        except Exception:
            pass

    def set_on_stop_session(self, handler) -> None:
        self._on_stop_session = handler

    def notify_stop_session(self) -> None:
        if callable(getattr(self, "_on_stop_session", None)):
            try:
                self._on_stop_session()
            except Exception:
                pass

    def handle_stop_session(self, countdown_minutes: Optional[float]) -> None:
        self.record_train_stop_time(countdown_minutes)
        self.notify_stop_session()

    def record_train_stop_time(self, countdown_minutes: Optional[float]) -> None:
        if not self._current_session_id or not self._current_patient_id:
            return
        try:
            self.service.update_train_stop_info(
                session_id=self._current_session_id,
                patient_id=self._current_patient_id,
                countdown_minutes=countdown_minutes,
            )
        except Exception:
            pass

    def get_current_patient_treat_session(self) -> Optional[Dict[str, Any]]:
        if not self._current_session_id:
            return None
        try:
            return self.service.get_patient_treat_session_by_session_id(self._current_session_id)
        except Exception:
            return None

    def get_patient_treat_session_by_session_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        try:
            return self.service.get_patient_treat_session_by_session_id(int(session_id))
        except Exception:
            return None

    def get_patient_treat_sessions_by_patient(self, patient_id: str) -> list[dict]:
        return self.service.get_patient_treat_sessions_by_patient(patient_id)

    def delete_patient_treat_sessions(self, session_ids: list[int]) -> int:
        return self.service.delete_patient_treat_sessions(session_ids)
