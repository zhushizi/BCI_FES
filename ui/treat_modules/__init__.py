"""
治疗页（tabWidget_2）按业务拆分的模块控制器。

目标：
- `TreatPageController` 只做导航/页面编排；
- 每个业务模块各自管理 UI 交互与调用各自的 App。
"""

from .stim_test_controller import StimTestController
from .impedance_test_controller import ImpedanceTestController
from .training_main_controller import TrainingMainController
from .training_sub_controller import TrainingSubController

__all__ = [
    "StimTestController",
    "ImpedanceTestController",
    "TrainingMainController",
    "TrainingSubController",
]

