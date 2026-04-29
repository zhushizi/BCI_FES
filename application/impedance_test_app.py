from __future__ import annotations

import logging
from typing import Any, Optional

from service.business.diagnostics.impedance_test_service import ImpedanceTestService


class ImpedanceTestApp:
    """脑阻抗测试应用层（占位）。"""

    def __init__(self, impedance_service: ImpedanceTestService):
        self.service = impedance_service
        self.logger = logging.getLogger(__name__)

    def start(self, patient_id: Optional[str] = None) -> bool:
        return self.service.start(patient_id)

    def stop(self) -> bool:
        return self.service.stop()

    def get_latest(self) -> Optional[dict[str, Any]]:
        return self.service.get_latest()

    def set_update_callback(self, callback) -> None:
        self.service.set_update_callback(callback)
