from __future__ import annotations

import logging

from application.session_app import SessionApp
from application.stim_test_app import StimTestApp


class ParadigmActionApp:
    """范式动作指令应用层：编排 session 与刺激指令下发。"""

    TIME_BYTE = 0x06
    START_STIM_TIME = 0x0A
    START_RISE_TIME = 0x05
    START_DOWN_TIME = 0x05
    CURRENT_MODE_START = 0xEF

    def __init__(self, session_app: SessionApp, stim_app: StimTestApp) -> None:
        self._session_app = session_app
        self._stim_app = stim_app
        self._logger = logging.getLogger(__name__)

    def handle_action_command(self, trial_index: int, action: str, channel: str) -> bool:
        patient_id = self._session_app.get_current_patient_id()
        if not patient_id:
            self._logger.warning("未找到当前患者，无法下发动作")
            return False
        treat_params = self._session_app.load_treat_params(patient_id)
        if not treat_params:
            self._logger.warning("未找到当前患者治疗参数，无法下发动作")
            return False

        scheme_idx = treat_params.left_scheme_idx if channel == "left" else treat_params.right_scheme_idx
        freq_idx = treat_params.left_freq_idx if channel == "left" else treat_params.right_freq_idx
        current = treat_params.left_grade if channel == "left" else treat_params.right_grade
        pulse_width_idx = treat_params.left_pulse_width_idx if channel == "left" else treat_params.right_pulse_width_idx

        scheme = int(scheme_idx or 0) + 1
        frequency = int(freq_idx or 20)
        current_val = int(current or 0)
        pulse_width = int(pulse_width_idx or 0) + 1
        leg_part = self._resolve_leg_part_from_session()
        device = self._stim_app.device_code_for(channel, leg_part)

        try:
            # 训练阶段使用会话内 StimPosition 计算设备码，避免被旧接口默认“小腿”覆盖。
            self._stim_app.send_advanced_params(
                device=device,
                current=self.CURRENT_MODE_START,
                stim_time=self.START_STIM_TIME,
                rise_time=self.START_RISE_TIME,
                down_time=self.START_DOWN_TIME,
            )
            self._stim_app.send_basic_params(
                device=device,
                waveform=scheme,
                pulse_width=pulse_width,
                frequency=frequency,
            )
            self._stim_app.send_advanced_params(
                device=device,
                current=current_val,
                stim_time=self.TIME_BYTE,
                rise_time=self.START_RISE_TIME,
                down_time=self.START_DOWN_TIME,
            )
            return True
        except Exception as exc:
            self._logger.error("下发动作指令失败: %s", exc)
            return False

    def _resolve_leg_part_from_session(self) -> str:
        """从当前会话解析刺激部位，兼容 gou/tai 与中文。"""
        try:
            session_data = self._session_app.get_current_patient_treat_session() or {}
        except Exception:
            session_data = {}
        raw = str(session_data.get("StimPosition") or "").strip().lower()
        if raw in ("tai", "大腿", "thigh"):
            return "大腿"
        if raw in ("gou", "小腿", "calf"):
            return "小腿"
        # 回退默认：与旧逻辑一致
        return "小腿"
