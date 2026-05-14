from __future__ import annotations

import logging
import time

from application.session_app import SessionApp
from application.stim_test_app import StimTestApp


class ParadigmActionApp:
    """范式动作指令应用层：编排 session 与刺激指令下发。"""

    TIME_BYTE = 0x06  # 训练第二帧刺激时长兜底默认；优先取 treat_params.stim_time_byte
    START_STIM_TIME = 0x0A
    START_RISE_TIME = 0x05
    START_DOWN_TIME = 0x05
    CURRENT_MODE_START = 0xEF
    CURRENT_MODE_STOP = 0xFF  # 高级参数帧「电流/启停」字节：结束当前模式（与 StimFrame 一致）
    # 高级参数帧第 9 字节（保留位）：训练范式下发专用；电刺激测试页仍用 UI 侧 0x02
    ADVANCED_RESERVED_TRAINING = 0xFF
    # 训练范式下发：高级起帧与高级电流帧之间间隔，便于下位机逐条识别（训练阶段不再发基础参数帧）
    INTER_CMD_DELAY_SEC = 1.0

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

        current = treat_params.left_grade if channel == "left" else treat_params.right_grade
        current_val = int(current or 0)
        # 刺激时长跟随 UI horizontalScrollBar_time_stim 设置（保存在 treat_params.stim_time_byte）
        stim_time_byte = int(getattr(treat_params, "stim_time_byte", 0) or 0) or self.TIME_BYTE
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
                reserved_byte=self.ADVANCED_RESERVED_TRAINING,
            )
            time.sleep(self.INTER_CMD_DELAY_SEC)
            self._stim_app.send_advanced_params(
                device=device,
                current=current_val,
                stim_time=stim_time_byte,
                rise_time=self.START_RISE_TIME,
                down_time=self.START_DOWN_TIME,
                reserved_byte=self.ADVANCED_RESERVED_TRAINING,
            )
            return True
        except Exception as exc:
            self._logger.error("下发动作指令失败: %s", exc)
            return False

    def send_stop_advanced_after_fc_a1(self, channel: str) -> None:
        """训练流程：下位机回报 FC A1 治疗完成后再发一条高级参数帧，电流字节 0xFF 显式停止。"""
        patient_id = self._session_app.get_current_patient_id()
        if not patient_id:
            self._logger.warning("FC A1 后下发停止帧：无当前患者，已跳过")
            return
        treat_params = self._session_app.load_treat_params(patient_id)
        if not treat_params:
            self._logger.warning("FC A1 后下发停止帧：无治疗参数，已跳过")
            return
        stim_time_byte = int(getattr(treat_params, "stim_time_byte", 0) or 0) or self.TIME_BYTE
        leg_part = self._resolve_leg_part_from_session()
        device = self._stim_app.device_code_for(channel, leg_part)
        try:
            self._stim_app.send_advanced_params(
                device=device,
                current=self.CURRENT_MODE_STOP,
                stim_time=stim_time_byte,
                rise_time=self.START_RISE_TIME,
                down_time=self.START_DOWN_TIME,
                reserved_byte=self.ADVANCED_RESERVED_TRAINING,
            )
        except Exception:
            self._logger.exception("FC A1 后下发训练停止高级参数失败")

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
