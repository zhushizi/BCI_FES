"""
治疗会话服务 - 负责一次治疗会话的持久化与查询。
仅使用 PatientTreatSession 表，不再使用 TreatmentSession 表。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.data import DatabaseService
from service.business.session.patient_treat_repository import PatientTreatSessionRepository


class SessionService:
    """治疗会话服务类（仅依赖 PatientTreatSession 表）"""

    TABLE_NAME = PatientTreatSessionRepository.TABLE_NAME
    PATIENT_TREAT_TABLE = PatientTreatSessionRepository.TABLE_NAME
    DATETIME_FORMAT = PatientTreatSessionRepository.DATETIME_FORMAT
    STATUS_ACTIVE = PatientTreatSessionRepository.STATUS_ACTIVE
    STATUS_ENDED = PatientTreatSessionRepository.STATUS_ENDED

    def __init__(self, db_service: DatabaseService):
        self.db = db_service
        self.logger = logging.getLogger(__name__)
        self._patient_treat_repo = PatientTreatSessionRepository(db_service, self.logger)
        self._patient_treat_repo.init_table()

    def upsert_patient_treat_session(
        self,
        *,
        session_id: int,
        patient_id: str,
        stim_channel_a: Optional[int] = None,
        stim_channel_b: Optional[int] = None,
        stim_scheme_ab: Optional[int] = None,
        stim_freq_ab: Optional[int] = None,
        stim_position: str = "",
        paradigm: str = "",
        total_train_duration: str = "",
        train_params: str = "",
        train_result: str = "",
    ) -> bool:
        return self._patient_treat_repo.upsert_patient_treat_session(
            session_id=session_id,
            patient_id=patient_id,
            stim_channel_a=stim_channel_a,
            stim_channel_b=stim_channel_b,
            stim_scheme_ab=stim_scheme_ab,
            stim_freq_ab=stim_freq_ab,
            stim_position=stim_position,
            paradigm=paradigm,
            total_train_duration=total_train_duration,
            train_params=train_params,
            train_result=train_result,
        )

    def update_train_start_time(
        self,
        *,
        session_id: int,
        patient_id: str,
        train_start_time: Optional[str] = None,
    ) -> bool:
        return self._patient_treat_repo.update_train_start_time(
            session_id=session_id,
            patient_id=patient_id,
            train_start_time=train_start_time,
        )

    def update_average_reaction_time(
        self,
        *,
        session_id: int,
        patient_id: str,
        average_reaction_time: float,
    ) -> bool:
        return self._patient_treat_repo.update_average_reaction_time(
            session_id=session_id,
            patient_id=patient_id,
            average_reaction_time=average_reaction_time,
        )

    def update_average_reaction_time_curve(
        self,
        *,
        session_id: int,
        patient_id: str,
        curve_path: str,
    ) -> bool:
        return self._patient_treat_repo.update_average_reaction_time_curve(
            session_id=session_id,
            patient_id=patient_id,
            curve_path=curve_path,
        )

    def update_reaction_time_curve(
        self,
        *,
        session_id: int,
        patient_id: str,
        curve_path: str,
    ) -> bool:
        return self._patient_treat_repo.update_reaction_time_curve(
            session_id=session_id,
            patient_id=patient_id,
            curve_path=curve_path,
        )

    def update_train_stop_info(
        self,
        *,
        session_id: int,
        patient_id: str,
        countdown_minutes: Optional[float],
    ) -> bool:
        return self._patient_treat_repo.update_train_stop_info(
            session_id=session_id,
            patient_id=patient_id,
            countdown_minutes=countdown_minutes,
        )

    def update_erds_path(
        self,
        *,
        session_id: int,
        patient_id: str,
        erds_path: str,
    ) -> bool:
        return self._patient_treat_repo.update_erds_path(
            session_id=session_id,
            patient_id=patient_id,
            erds_path=erds_path,
        )

    def get_patient_treat_session_by_session_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        return self._patient_treat_repo.get_patient_treat_session_by_session_id(session_id)

    def get_patient_treat_sessions_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._patient_treat_repo.get_patient_treat_sessions_by_patient(patient_id)

    def delete_patient_treat_sessions(self, session_ids: List[int]) -> int:
        return self._patient_treat_repo.delete_patient_treat_sessions(session_ids)

    def start_session(
        self,
        patient_info: Dict[str, Any],
        plan_name: str = "",
        body_part: str = "",
        paradigm: str = "",
        start_time: Optional[str] = None,
    ) -> Optional[int]:
        """创建新会话并返回 SessionId（仅写入 PatientTreatSession）"""
        if not patient_info:
            self.logger.error("创建会话失败：patient_info 为空")
            return None
        session_id = self._patient_treat_repo.create_session(
            patient_info=patient_info,
            plan_name=plan_name,
            body_part=body_part,
            paradigm=paradigm,
            start_time=start_time,
        )
        if not session_id:
            return None
        patient_id = self._patient_treat_repo.normalize_patient_id(
            patient_info.get("PatientId") or patient_info.get("patient_id")
        )
        try:
            self._patient_treat_repo.upsert_patient_treat_session(
                session_id=session_id,
                patient_id=patient_id,
                stim_position=body_part or "",
                paradigm=paradigm or "",
            )
        except Exception:
            pass
        return session_id

    def update_stim_params(
        self,
        *,
        session_id: int,
        patient_id: str,
        left_grade: Optional[int] = None,
        right_grade: Optional[int] = None,
        left_scheme_idx: Optional[int] = None,
        right_scheme_idx: Optional[int] = None,
        left_freq_idx: Optional[int] = None,
        right_freq_idx: Optional[int] = None,
    ) -> bool:
        scheme_ab = left_scheme_idx if left_scheme_idx is not None else right_scheme_idx
        freq_ab = left_freq_idx if left_freq_idx is not None else right_freq_idx
        return self._patient_treat_repo.upsert_patient_treat_session(
            session_id=session_id,
            patient_id=patient_id,
            stim_channel_a=None if left_grade is None else int(left_grade),
            stim_channel_b=None if right_grade is None else int(right_grade),
            stim_scheme_ab=None if scheme_ab is None else int(scheme_ab),
            stim_freq_ab=None if freq_ab is None else int(freq_ab),
        )

    def end_session(self, session_id: int, reason: str = "manual_exit", end_time: Optional[str] = None) -> bool:
        """结束会话"""
        return self._patient_treat_repo.end_session(session_id, reason=reason, end_time=end_time)

    def get_session_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        return self._patient_treat_repo.get_session_by_id(session_id)

    def get_active_sessions_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._patient_treat_repo.get_active_sessions_by_patient(patient_id)
