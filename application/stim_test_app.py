from __future__ import annotations

import logging
from typing import Optional

from service.business.hardware.stim_test_service import StimTestService


class StimTestApp:
    """
    电刺激测试应用层（用例编排入口）。

    UI 只依赖 App；Service 负责业务与外部依赖（硬件/协议）。
    """

    def __init__(self, stim_service: StimTestService):
        self.service = stim_service
        self.logger = logging.getLogger(__name__)

    def start_dual(self) -> bool:
        return self.service.start_dual()

    def stop_dual(self) -> bool:
        return self.service.stop_dual()

    def start_treatment_channel(self, channel: str) -> bool:
        return self.service.start_treatment_channel(channel)

    def set_treatment_params(
        self,
        scheme: int,
        frequency: int,
        current: int,
        channel: Optional[str] = None,
        time_byte: Optional[int] = None,
    ) -> bool:
        return self.service.set_treatment_params(
            scheme=scheme,
            frequency=frequency,
            current=current,
            channel=channel,
            time_byte=time_byte,
        )

    def set_params(self, scheme: int, frequency: int, current: int, channel: Optional[str] = None) -> bool:
        return self.service.set_params(
            scheme=scheme,
            frequency=frequency,
            current=current,
            channel=channel,
        )

