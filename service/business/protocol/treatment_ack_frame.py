from __future__ import annotations

from service.business.protocol.stim_frame import StimFrame


class TreatmentAckFrame:
    """下位机治疗完成应答（与下发刺激帧同壳 55 AA 0D）。

    字节布局与 StimFrame 一致：帧类型位为 0xFC（治疗完成标志），其后第一字节为 0xA1 表示治疗成功。
    即相对帧起点 1-based：第 5 字节 = 0xFC，第 6 字节 = 0xA1（0-based 下标 4、5）。
    """

    _HEADER = StimFrame.FRAME_HEADER
    _LENGTH = StimFrame.FRAME_LENGTH
    FLAG_TREAT_COMPLETE = 0xFC
    SUCCESS_STATUS = 0xA1
    _DEVICES = (
        StimFrame.DEVICE_LEFT_THIGH,
        StimFrame.DEVICE_LEFT_CALF,
        StimFrame.DEVICE_RIGHT_THIGH,
        StimFrame.DEVICE_RIGHT_CALF,
    )
    # 从帧首到判定位（含）：55 aa 0d [dev] fc a1 → 至少 6 字节
    _MIN_SPAN = 6

    @classmethod
    def buffer_contains_success_ack(cls, buf: bytes) -> bool:
        """在缓冲中查找任意对齐的 55 AA 0D 帧起点，且帧类型 FC、下一字节 A1。"""
        n = len(buf)
        if n < cls._MIN_SPAN:
            return False
        last_i = n - cls._MIN_SPAN
        for i in range(last_i + 1):
            if buf[i : i + 2] != cls._HEADER:
                continue
            if buf[i + 2] != cls._LENGTH:
                continue
            if buf[i + 3] not in cls._DEVICES:
                continue
            if buf[i + 4] == cls.FLAG_TREAT_COMPLETE and buf[i + 5] == cls.SUCCESS_STATUS:
                return True
        return False
