from __future__ import annotations

import logging
from typing import Optional, Tuple

from application.config_app import ConfigApp
from application.config_paths import resolve_config_path
from application.session_app import SessionApp
from service.business.ws.ws_notify_service import WsNotifyService


class TreatFlowApp:
    """治疗流程应用层：编排会话创建与 WS 通知。"""

    def __init__(
        self,
        session_app: SessionApp,
        ws_service: Optional[WsNotifyService] = None,
        config_app: Optional[ConfigApp] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._session_app = session_app
        self._ws_service = ws_service
        self._config_app = config_app
        self._logger = logger or logging.getLogger(__name__)
        self._current_patient_snapshot: dict = {}

    def start_treat_from_button(self, patient_snapshot: dict, button_name: str) -> Tuple[Optional[str], str, str, str]:
        pid = self._extract_patient_id(patient_snapshot)
        if not pid or not button_name:
            return None, "", "", ""
        self._current_patient_snapshot = dict(patient_snapshot or {})
        plan_name, body_part, paradigm = self.parse_treat_button_info(button_name)
        if plan_name:
            self._session_app.start_session(
                patient_id=pid,
                plan_name=plan_name,
                body_part=body_part,
                paradigm=paradigm,
                patient_snapshot=patient_snapshot,
            )
            self._send_paradigm_selected(plan_name, patient_snapshot)
        return pid, plan_name, body_part, paradigm

    def parse_treat_button_info(self, button_name: str) -> Tuple[str, str, str]:
        name = (button_name or "").strip()
        if not name:
            return "", "", ""
        parts = name.replace("pushButton_", "").split("_")
        body_key = parts[0] if parts else ""
        paradigm_key = parts[1] if len(parts) > 1 else ""
        body_map = {"gou": "小腿", "tai": "大腿"}
        paradigm_map = {"ssvep": "SSVEP", "ssmvep": "SSMVEP", "mi": "MI", "mix": "MIX"}
        body_display = body_map.get(body_key, "")
        paradigm_display = paradigm_map.get(paradigm_key, "")
        plan_name = "-".join(p for p in [body_display, paradigm_display] if p)
        return plan_name, body_key, paradigm_key

    def resolve_paradigm_exe_from_session(self) -> Tuple[Optional[str], Optional[str]]:
        session_data = None
        try:
            session_data = self._session_app.get_current_patient_treat_session()
        except Exception:
            session_data = None
        data = session_data or {}
        body_part = str(data.get("StimPosition") or "").strip().lower()
        paradigm = str(data.get("Paradigm") or "").strip().lower()
        if paradigm in ("ssv", "ssvep"):
            paradigm = "ssvep"
        elif paradigm in ("ssm", "ssmvep"):
            paradigm = "ssmvep"
        elif paradigm != "mi":
            paradigm = ""

        exe_key_map = {
            ("gou", "ssmvep"): "ssmvep_exe_gou",
            ("gou", "ssvep"): "ssvep_exe_gou",
            ("gou", "mi"): "mi_exe_gou",
            ("tai", "ssmvep"): "ssmvep_exe_tai",
            ("tai", "ssvep"): "ssvep_exe_tai",
            ("tai", "mi"): "mi_exe_tai",
        }
        class_map = {"ssmvep": "SSMVEP", "ssvep": "SSVEP", "mi": "MI"}
        base_exe_key = exe_key_map.get((body_part, paradigm)) if body_part and paradigm else None
        if not base_exe_key or not self._config_app:
            return None, (class_map.get(paradigm) if paradigm else None)
        try:
            config = self._config_app.load()
        except Exception:
            config = {}
        leg_side = self._resolve_leg_side(data)
        candidate_keys = self._build_candidate_exe_keys(base_exe_key, leg_side)
        exe_path = None
        for key in candidate_keys:
            value = str(config.get(key) or "").strip()
            if value:
                exe_path = resolve_config_path(value)
                break
        return exe_path, class_map.get(paradigm)

    def send_impedance_close(self) -> None:
        if not self._ws_service:
            return
        try:
            self._ws_service.send_notification(
                "main.set_ImpedanceMode",
                {"open_or_close": "close"},
            )
        except Exception:
            pass

    def _send_paradigm_selected(self, plan_name: str, patient_snapshot: dict) -> None:
        if not self._ws_service:
            return
        patient_name = str((patient_snapshot or {}).get("Name") or "").strip()
        paradigm_name = str(plan_name or "").strip()
        if not patient_name or not paradigm_name:
            return
        try:
            self._ws_service.send_notification(
                "main.Inform",
                {"patient": patient_name, "paradigm": paradigm_name},
            )
        except Exception:
            pass

    @staticmethod
    def _extract_patient_id(patient: dict | None) -> Optional[str]:
        if not patient:
            return None
        pid = patient.get("PatientId") or patient.get("Name") or ""
        pid = str(pid).strip()
        return pid or None

    def _resolve_leg_side(self, session_data: dict) -> str:
        """返回 left/right/both/unknown。"""
        leg_value = self._extract_leg_value(session_data)
        leg_lower = leg_value.lower()
        if "左" in leg_value and "右" not in leg_value:
            return "left"
        if "右" in leg_value and "左" not in leg_value:
            return "right"
        if "双" in leg_value or ("左" in leg_value and "右" in leg_value):
            return "both"
        if "left" in leg_lower and "right" not in leg_lower:
            return "left"
        if "right" in leg_lower and "left" not in leg_lower:
            return "right"
        if "both" in leg_lower:
            return "both"
        return "unknown"

    def _extract_leg_value(self, session_data: dict) -> str:
        patient_id = str((session_data or {}).get("PatientId") or "").strip()
        leg = str((self._current_patient_snapshot or {}).get("Leg") or "").strip()
        if leg:
            return leg
        if not patient_id:
            return ""
        try:
            patient = self._session_app.patient_app.get_patient_by_id(patient_id)
        except Exception:
            patient = None
        return str((patient or {}).get("Leg") or "").strip()

    @staticmethod
    def _build_candidate_exe_keys(base_exe_key: str, leg_side: str) -> list[str]:
        if leg_side == "left":
            return [f"{base_exe_key}_left", base_exe_key, f"{base_exe_key}_right"]
        if leg_side == "right":
            return [f"{base_exe_key}_right", base_exe_key, f"{base_exe_key}_left"]
        # 双腿或未知时，优先兼容旧键，其次回退到 left/right。
        return [base_exe_key, f"{base_exe_key}_left", f"{base_exe_key}_right"]
