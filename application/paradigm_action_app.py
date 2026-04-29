from __future__ import annotations

import logging

from application.session_app import SessionApp
from application.stim_test_app import StimTestApp


class ParadigmActionApp:
    """范式动作指令应用层：编排 session 与刺激指令下发。"""

    TIME_BYTE = 0x06

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

        scheme = int(scheme_idx or 0) + 1
        frequency = int(freq_idx or 0)
        current_val = int(current or 0)

        try:
            self._stim_app.start_treatment_channel(channel)
            self._stim_app.set_treatment_params(
                scheme=scheme,
                frequency=frequency,
                current=current_val,
                channel=channel,
                time_byte=self.TIME_BYTE,
            )
            return True
        except Exception as exc:
            self._logger.error("下发动作指令失败: %s", exc)
            return False
