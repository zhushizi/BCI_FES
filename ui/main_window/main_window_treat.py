from __future__ import annotations

"""
治疗页控制器（页面编排层）

职责边界（框架阶段已经按你说的拆成四块）：
- TreatPageController：只做 tab 导航/标题切换/模块之间编排
- 业务模块控制器：
  - StimTestController（电刺激测试，tabWidget_2 index=0）
  - ImpedanceTestController（脑阻抗测试，tabWidget_2 index=1）
  - TrainingMainController（训练主屏，tabWidget_2 index=2）
  - TrainingSubController（训练副屏，sub_window.ui tabWidget index=1）
"""

import logging

from application.patient_app import PatientApp
from application.stim_test_app import StimTestApp
from application.impedance_test_app import ImpedanceTestApp
from application.training_main_app import TrainingMainApp
from application.training_sub_app import TrainingSubApp
from ui.main_window.sub_window import SubWindow
from ui.main_window.main_window_treat_sections import TreatNavigation, TreatSessionGuard, TreatWsBridge
from ui.treat_modules import (
    StimTestController,
    ImpedanceTestController,
    TrainingMainController,
    TrainingSubController,
)


class TreatPageController:
    """负责预处理页（tabWidget_main 的 tab2）及内部 tabWidget_2 的导航（编排层）。"""

    def __init__(
        self,
        ui,
        on_return_home=None,
        sub_window: SubWindow | None = None,
        patient_app: PatientApp | None = None,
        session_app=None,
        stim_test_app: StimTestApp | None = None,
        impedance_app: ImpedanceTestApp | None = None,
        training_main_app: TrainingMainApp | None = None,
        training_sub_app: TrainingSubApp | None = None,
        ws_service=None,
        config_app=None,
        reaction_time_app=None,
        training_flow_app=None,
        paradigm_exe_path: str | None = None,
        hide_subprocess_console: bool = False,
    ):
        self.ui = ui
        self._logger = logging.getLogger(__name__)
        self._on_return_home = on_return_home
        self.sub_window = sub_window
        self.patient_app = patient_app
        self.session_app = session_app
        self.ws_service = ws_service
        self._ws_bridge = TreatWsBridge(self)
        self._session_guard = TreatSessionGuard(self)
        self._nav = TreatNavigation(self)

        # 四个模块控制器（按 tab 拆分）
        self.stim_ctrl = StimTestController(ui, session_app=session_app, stim_app=stim_test_app)
        self.impedance_ctrl = ImpedanceTestController(ui, patient_app=patient_app, impedance_app=impedance_app)
        self.training_main_ctrl = TrainingMainController(
            ui,
            patient_app=patient_app,
            session_app=session_app,
            training_app=training_main_app,
            config_app=config_app,
            reaction_time_app=reaction_time_app,
            training_flow_app=training_flow_app,
            on_countdown_finished=self._on_countdown_finished_return_home,
            on_shut_down_return_home=self._on_return_home,
        )
        self.training_sub_ctrl = TrainingSubController(
            sub_window=sub_window,
            patient_app=patient_app,
            training_app=training_sub_app,
            paradigm_exe_path=paradigm_exe_path,
            hide_console=hide_subprocess_console,
        )

        self._current_patient: dict | None = None

    # ---------- 对外接口 ----------
    def bind_signals(self) -> None:
        """绑定预处理相关按钮/Tab 事件（导航层 + 下沉到模块控制器）"""
        # 导航按钮
        self._nav.bind()

        # 下沉：模块自身信号绑定
        self.stim_ctrl.bind_signals()
        self.impedance_ctrl.bind_signals()
        self.training_main_ctrl.bind_signals()
        self.training_sub_ctrl.bind_signals()

    def enter_preprocess_page(self) -> None:
        """进入预处理主页面并重置子页状态"""
        self._nav.enter_preprocess_page()

    def set_current_patient(self, patient: dict | None) -> None:
        """设置当前患者并恢复缓存的左右通道档位/训练参数等（患者绑定）"""
        self._current_patient = patient
        pid = self._extract_patient_id(patient)

        # 统一把 patient_id 往下传
        self.stim_ctrl.set_current_patient(patient)
        self.impedance_ctrl.set_current_patient(pid)
        self.training_main_ctrl.set_current_patient(pid)
        self.training_sub_ctrl.set_current_patient(pid)

    def _on_countdown_finished_return_home(self) -> None:
        """倒计时结束时用户选择「是」：返回主页面。"""
        if callable(self._on_return_home):
            self._on_return_home()

    def on_exit_treat_page(self) -> None:
        """离开治疗页时调用：停止治疗并保存当前档位（模块各自处理）。"""
        self.stim_ctrl.on_exit()
        self.impedance_ctrl.on_exit()
        self.training_main_ctrl.on_exit()
        # 副屏不一定要退出；这里只保留占位

    # ---------- 内部事件（导航/编排） ----------
    def _on_preprocess_next(self) -> None:
        """预处理页：下一步，进入 tabWidget_2 的第二页（脑阻抗测试）"""
        self._nav.on_preprocess_next()

    def _on_preprocess_return(self) -> None:
        """预处理页：返回逻辑（tab_3->tab_2->tab_1；或回首页）"""
        self._nav.on_preprocess_return()

    def _send_impedance_close_and_start_training(self) -> None:
        """从阻抗页返回时：关闭阻抗检测"""
        self._ws_bridge.close_impedance_mode()

    def _send_impedance_open(self) -> None:
        """从训练页返回阻抗页时：开启阻抗检测"""
        self._ws_bridge.send_impedance_open()

    def _on_main_tab_changed(self, index: int) -> None:
        """主级 tab 切换时，若返回主界面，重置子页标题"""
        self._nav.on_main_tab_changed(index)

    def _on_sub_tab_changed(self, index: int) -> None:
        """子级 tab 切换时，进入训练主屏刷新信息"""
        self._nav.on_sub_tab_changed(index)

    def _update_preprocess_title(self, image_name: str) -> None:
        """根据子页更新标题背景与位置"""
        self._nav.update_preprocess_title(image_name)

    def _confirm_exit_if_session_active(self) -> bool:
        return self._session_guard.confirm_exit_if_session_active()

    def end_session_by_timeout(self) -> None:
        """预留：治疗时间到达后结束会话并回主页面。"""
        if self.session_app and self.session_app.has_active_session():
            self.session_app.end_session("time_up")
        if callable(self._on_return_home):
            self._on_return_home()
        self.stim_ctrl.on_exit()

    def _extract_patient_id(self, patient: dict | None) -> str | None:
        if not patient:
            return None
        pid = patient.get("PatientId") or patient.get("Name") or ""
        pid = str(pid).strip()
        return pid or None
