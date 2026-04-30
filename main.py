"""
BCI硬件控制系统主程序
直接启动登录页面
"""

import sys
import argparse
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 日志由 main() 内根据 config 统一配置，见 infrastructure.logging_config
logger = logging.getLogger(__name__)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication

from ui.core.app_icon import apply_application_icon

# 基础设施 & 服务层（组合根负责装配，业务层对下游透明）
from infrastructure.data import DatabaseService
from service.business.config.config_service import ConfigService
from infrastructure.hardware.serial_hardware import SerialHardware
from infrastructure.storage.erds_storage import ErdsStorage
from infrastructure.storage.reaction_time_storage import ReactionTimeStorage
from service.business.storage.erds_storage_service import ErdsStorageService
from service.business.storage.reaction_time_storage_service import ReactionTimeStorageService
from service.business.ws.ws_notify_service import WsNotifyService
from service.business.decoder.decoder_process_service import DecoderProcessService
from service.user import UserLoginService, PatientService, SchemeService, ReportService
from service.business.hardware.stim_test_service import StimTestService
from service.business.diagnostics.impedance_test_service import ImpedanceTestService
from service.business.training.training_main_service import TrainingMainService
from service.business.training.training_sub_service import TrainingSubService
from service.business.ws import WsMessageRouter
from service.business.hardware.hardware_pingpong_service import HardwarePingPongService
from service.business.session.session_service import SessionService

from infrastructure.communication.websocket_service import MainWebSocketService
from infrastructure.decoder.decoder_manager import DecoderProcessManager

# 应用层
from application import (
    UserApp,
    PatientApp,
    SchemeApp,
    ReportApp,
    HardwareApp,
    DecoderApp,
    ConfigApp,
    ReactionTimeApp,
    ParadigmActionApp,
    WsMessageApp,
    TreatFlowApp,
    TrainingFlowApp,
    HardwareConfigApp,
    StimTestApp,
    ImpedanceTestApp,
    TrainingMainApp,
    TrainingSubApp,
    SessionApp,
)

# UI
from infrastructure.logging_config import setup_logging
from ui.core.resource_loader import ensure_resources_loaded
from ui.core.decoder_log_formatter import summarize_decoder_session_info, log_json
from ui.dialogs.login import LoginWindow
from ui.main_window.main_window import MainWindow
from ui.main_window.sub_window import SubWindow


@dataclass(frozen=True)
class AppConfig:
    # 串口默认值改由 config.json 的 NES_port 或命令行 --com 提供，这里不再硬编码
    com_port: str = ""
    ws_url: str = "ws://127.0.0.1:8080"
    log_receive_enabled: bool = False
    log_heartbeat_enabled: bool = False
    ws_enable_heartbeat: bool = False
    ws_max_message_size: Optional[int] = 4 * 1024 * 1024
    enable_sub_window: bool = True
    swap_screens: bool = False
    paradigm_exe_path: Optional[str] = None
    decoder_port: Optional[str] = None
    decoder_exe_path: Optional[str] = None
    hide_subprocess_console: bool = False


@dataclass(frozen=True)
class ServiceBundle:
    db_service: DatabaseService
    config_service: ConfigService
    erds_storage_service: ErdsStorageService
    reaction_time_storage_service: ReactionTimeStorageService
    user_service: UserLoginService
    patient_service: PatientService
    scheme_service: SchemeService
    report_service: ReportService
    session_service: SessionService
    serial_hw: SerialHardware
    hardware_service: StimTestService
    pingpong_service: HardwarePingPongService
    ws_service: MainWebSocketService
    ws_notify_service: WsNotifyService
    impedance_service: ImpedanceTestService
    ws_router: WsMessageRouter


@dataclass(frozen=True)
class AppBundle:
    user_app: UserApp
    patient_app: PatientApp
    scheme_app: SchemeApp
    report_app: ReportApp
    session_app: SessionApp
    hardware_app: HardwareApp
    decoder_app: DecoderApp
    config_app: ConfigApp
    reaction_time_app: ReactionTimeApp
    paradigm_action_app: ParadigmActionApp
    treat_flow_app: TreatFlowApp
    training_flow_app: TrainingFlowApp
    hardware_config_app: HardwareConfigApp
    stim_app: StimTestApp
    impedance_app: ImpedanceTestApp
    training_main_app: TrainingMainApp
    training_sub_app: TrainingSubApp


def load_resources() -> None:
    """
    加载UI资源文件（resources_rc.py）
    统一在程序启动时加载，以便后续所有页面使用
    """
    ensure_resources_loaded()

def build_services(config: AppConfig) -> ServiceBundle:
    """组装基础设施 + 服务层。"""
    db_service = DatabaseService()
    config_service = ConfigService()
    erds_storage = ErdsStorage()
    reaction_time_storage = ReactionTimeStorage()
    erds_storage_service = ErdsStorageService(erds_storage)
    reaction_time_storage_service = ReactionTimeStorageService(reaction_time_storage)
    user_service = UserLoginService(db_service)
    patient_service = PatientService(db_service)
    scheme_service = SchemeService(db_service)
    report_service = ReportService(db_service)
    session_service = SessionService(db_service)

    # 硬件服务（串口与治疗命令）
    serial_hw = SerialHardware(
        port = config.com_port,
        log_receive_enabled = config.log_receive_enabled,
        log_heartbeat_enabled = config.log_heartbeat_enabled,
    )
    if not serial_hw.connect():
        logger.warning("串口连接失败: %s", config.com_port)
    # 治疗/电刺激指令服务（原 HardwareTreatmentService 已迁移到 StimTestService）
    hardware_service = StimTestService(serial_hw)
    pingpong_service = HardwarePingPongService(serial_hw)

    # 三方通讯（主控角色）：连接本地 WebSocket(JSON-RPC) 服务器并注册 main
    # 主控端不需要主动发送心跳（避免对端回 pong 导致控制台刷屏）；仍保留被动处理对端 ping 的兼容逻辑
    ws_service = MainWebSocketService(
        url = config.ws_url,
        client_type = "main",
        enable_heartbeat = config.ws_enable_heartbeat,
        max_message_size = config.ws_max_message_size,
    )
    ws_notify_service = WsNotifyService(ws_service)

    # WS 消息路由（服务层）：集中处理 decoder.ready / system.ping / paradigm.action_command 等
    impedance_service = ImpedanceTestService(ws_service)
    ws_router = WsMessageRouter(
        ws_service,
        impedance_service=impedance_service,
        stim_service=hardware_service,
        serial_hw=serial_hw,
    )
    ws_router.register_handlers()

    ws_service.start()

    return ServiceBundle(
        db_service=db_service,
        config_service=config_service,
        erds_storage_service=erds_storage_service,
        reaction_time_storage_service=reaction_time_storage_service,
        user_service=user_service,
        patient_service=patient_service,
        scheme_service=scheme_service,
        report_service=report_service,
        session_service=session_service,
        serial_hw=serial_hw,
        hardware_service=hardware_service,
        pingpong_service=pingpong_service,
        ws_service=ws_service,
        ws_notify_service=ws_notify_service,
        impedance_service=impedance_service,
        ws_router=ws_router,
    )


def build_apps(services: ServiceBundle, decoder_manager: DecoderProcessManager) -> AppBundle:
    """组装应用层。"""
    user_app = UserApp(services.user_service)
    patient_app = PatientApp(services.patient_service)
    scheme_app = SchemeApp(services.scheme_service)
    report_app = ReportApp(services.report_service)
    session_app = SessionApp(patient_app, services.session_service)
    services.ws_router.set_on_stop_session(session_app.handle_stop_session)

    # 旧硬件应用层（保留兼容）
    hardware_app = HardwareApp(services.hardware_service)
    decoder_process_service = DecoderProcessService(decoder_manager)
    decoder_app = DecoderApp(decoder_process_service)
    config_app = ConfigApp(services.config_service)
    reaction_time_app = ReactionTimeApp(services.reaction_time_storage_service)
    hardware_config_app = HardwareConfigApp(config_app, hardware_app, decoder_app, logger)

    # 四模块：Service + App（先搭框架，细节后续实现）
    # 电刺激测试也复用同一份服务（避免重复实现/重复注入）
    stim_app = StimTestApp(services.hardware_service)
    impedance_app = ImpedanceTestApp(services.impedance_service)

    paradigm_action_app = ParadigmActionApp(session_app, stim_app)
    services.ws_router.set_on_action_command(paradigm_action_app.handle_action_command)

    ws_message_app = WsMessageApp(
        services.ws_notify_service,
        logger,
        summarize_session_info=summarize_decoder_session_info,
        log_json=lambda title, params: log_json(logger, title, params),
    )
    services.ws_router.set_on_decoder_ready(ws_message_app.handle_decoder_ready)
    services.ws_router.set_on_decoder_session_info(ws_message_app.handle_decoder_session_info)
    services.ws_router.set_on_system_ping(ws_message_app.build_system_ping_result)

    training_main_service = TrainingMainService(services.ws_service)
    treat_flow_app = TreatFlowApp(session_app, services.ws_notify_service, config_app, logger)
    training_sub_service = TrainingSubService(services.ws_service)
    training_main_app = TrainingMainApp(session_app, training_main_service, services.erds_storage_service)
    training_flow_app = TrainingFlowApp(session_app, training_main_app, logger)
    training_sub_app = TrainingSubApp(session_app, training_sub_service)
    try:
        training_sub_app.connect()
    except Exception:
        logger.exception("TrainingSubApp 连接失败")

    return AppBundle(
        user_app=user_app,
        patient_app=patient_app,
        scheme_app=scheme_app,
        report_app=report_app,
        session_app=session_app,
        hardware_app=hardware_app,
        decoder_app=decoder_app,
        config_app=config_app,
        reaction_time_app=reaction_time_app,
        paradigm_action_app=paradigm_action_app,
        treat_flow_app=treat_flow_app,
        training_flow_app=training_flow_app,
        hardware_config_app=hardware_config_app,
        stim_app=stim_app,
        impedance_app=impedance_app,
        training_main_app=training_main_app,
        training_sub_app=training_sub_app,
    )

def connect_shutdown(
    app: QApplication,
    services: ServiceBundle,
    decoder_app: Optional[DecoderApp] = None,
    ws_server_process=None,
) -> None:
    """应用退出时确保断开并关闭本程序启动的服务器进程。"""
    app.aboutToQuit.connect(lambda: services.ws_service.stop())
    app.aboutToQuit.connect(lambda: services.serial_hw.disconnect())
    if decoder_app:
        app.aboutToQuit.connect(decoder_app.stop)
    if ws_server_process is not None:
        def stop_ws_server() -> None:
            try:
                if ws_server_process.poll() is None:
                    ws_server_process.terminate()
                    ws_server_process.wait(timeout=3)
            except Exception:
                try:
                    ws_server_process.kill()
                except Exception:
                    pass
        app.aboutToQuit.connect(stop_ws_server)


def safe_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    try:
        func(*args, **kwargs)
    except Exception:
        logger.exception("调用失败: %s", getattr(func, "__name__", "unknown"))


def create_sub_window(enable_sub_window: bool = True, screen_index: int = 1) -> Optional[SubWindow]:
    if not enable_sub_window:
        return None
    try:
        sub_window = SubWindow()
        sub_window.show_on_screen(screen_index)
        return sub_window
    except Exception:
        logger.exception("副屏窗口创建或显示失败")
        return None


def set_window_on_screen(widget, screen_index: int) -> None:
    try:
        screens = QGuiApplication.screens()
        if not screens:
            return
        if 0 <= screen_index < len(screens):
            target = screens[screen_index]
        else:
            target = screens[-1]
        if widget.windowHandle():
            widget.windowHandle().setScreen(target)
        widget.setGeometry(target.geometry())
    except Exception:
        logger.exception("设置窗口屏幕失败")


def create_main_window(
    apps: AppBundle,
    services: ServiceBundle,
    sub_window: Optional[SubWindow],
    paradigm_exe_path: Optional[str],
    decoder_port: Optional[str],
    hide_subprocess_console: bool = False,
) -> MainWindow:
    main_window = MainWindow(
        apps.user_app,
        apps.patient_app,
        apps.scheme_app,
        sub_window,
        apps.report_app,
        apps.session_app,
        apps.hardware_app,
        services.pingpong_service,
        apps.stim_app,
        apps.impedance_app,
        apps.training_main_app,
        apps.training_sub_app,
        services.ws_service,
        paradigm_exe_path,
        decoder_port,
        apps.decoder_app,
        apps.config_app,
        apps.reaction_time_app,
        apps.treat_flow_app,
        apps.training_flow_app,
        apps.hardware_config_app,
        hide_subprocess_console=hide_subprocess_console,
    )

    # 阻抗/脑电回调：WS 线程 -> Qt UI 线程
    safe_call(apps.impedance_app.set_update_callback, main_window.impedance_value_received.emit)
    safe_call(apps.training_main_app.set_wave_callback, main_window.eeg_frame_received.emit)
    safe_call(apps.training_main_app.set_intent_callback, main_window.intent_result_received.emit)

    if sub_window:
        # 主窗销毁时，确保副屏同步关闭
        safe_call(main_window.destroyed.connect, lambda _=None: sub_window.close())
        # 主窗按钮联动副屏：最小化/关闭
        if hasattr(main_window.ui, "pushButton_quit"):
            safe_call(main_window.ui.pushButton_quit.clicked.connect, sub_window.close)

    return main_window


def run_login_flow(
    apps: AppBundle,
    services: ServiceBundle,
    enable_sub_window: bool,
    swap_screens: bool,
    paradigm_exe_path: Optional[str],
    decoder_port: Optional[str],
    hide_subprocess_console: bool = False,
) -> None:
    """创建并维护登录流程。"""
    login_window = LoginWindow(apps.user_app)
    main_window: Optional[MainWindow] = None
    sub_window: Optional[SubWindow] = None

    def show_login() -> None:
        login_window.showFullScreen()
        set_window_on_screen(login_window, 1 if swap_screens else 0)
        login_window.raise_()
        login_window.activateWindow()

    def on_login_success(user_info: dict) -> None:
        nonlocal main_window
        nonlocal sub_window

        login_window.hide()
        sub_screen = 0 if swap_screens else 1
        main_screen = 1 if swap_screens else 0
        sub_window = create_sub_window(enable_sub_window=enable_sub_window, screen_index=sub_screen)
        main_window = create_main_window(
            apps,
            services,
            sub_window,
            paradigm_exe_path,
            decoder_port,
            hide_subprocess_console=hide_subprocess_console,
        )

        def on_logout() -> None:
            nonlocal main_window
            nonlocal sub_window
            if main_window:
                main_window.close()
                main_window = None
            if sub_window:
                sub_window.close()
                sub_window = None
            # 清理阻抗回调，避免悬挂引用
            safe_call(apps.impedance_app.set_update_callback, None)
            show_login()

        main_window.logout_requested.connect(on_logout)
        main_window.showFullScreen()
        set_window_on_screen(main_window, main_screen)

    def on_login_cancelled() -> None:
        sys.exit(0)

    login_window.login_success.connect(on_login_success)
    login_window.login_cancelled.connect(on_login_cancelled)
    show_login()


def load_startup_config() -> dict:
    config_service = ConfigService()
    return config_service.load()


def _detect_keyword_ports() -> tuple[Optional[str], Optional[str]]:
    """
    基于串口描述关键字检测两类设备端口：
    - 含“串行设备” -> decoder_port
    - 含“CH340” -> NES_port
    """
    try:
        details = SerialHardware.list_available_port_details()
    except Exception:
        return None, None
    decoder_port = None
    nes_port = None
    for item in details:
        device = str(item.get("device") or "").strip()
        if not device:
            continue
        haystack = " ".join(
            [
                str(item.get("description") or ""),
                str(item.get("manufacturer") or ""),
                str(item.get("hwid") or ""),
            ]
        ).upper()
        if decoder_port is None and "串行设备" in haystack:
            decoder_port = device
        if nes_port is None and "CH340" in haystack:
            nes_port = device
        if decoder_port and nes_port:
            break
    return decoder_port, nes_port


def _subprocess_creationflags(hide_console: bool):
    """Windows 下 hide_console 时用 CREATE_NO_WINDOW 不弹窗，否则用 CREATE_NEW_CONSOLE。"""
    if sys.platform != "win32":
        return 0
    if hide_console:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0


def start_websocket_server(exe_path: Optional[str], hide_console: bool = False):
    """
    根据配置启动 websocket_exe，未配置或文件不存在时跳过。
    Windows 下 hide_console 为 True 时不弹终端窗口。
    返回 Popen 进程对象，供退出时关闭；未启动则返回 None。
    """
    if not exe_path:
        logger.info("未配置 websocket_exe，跳过启动")
        return None
    exe_file = Path(exe_path)
    if not exe_file.is_file():
        logger.warning("websocket_exe 不存在: %s", exe_file)
        return None
    try:
        creation_flags = _subprocess_creationflags(hide_console)
        proc = subprocess.Popen(
            [str(exe_file)],
            cwd=str(exe_file.parent),
            creationflags=creation_flags,
        )
        logger.info("已启动 websocket_exe: %s", exe_file)
        return proc
    except Exception:
        logger.exception("启动 websocket_exe 失败: %s", exe_file)
        return None


def main() -> None:
    """主函数"""
    config_data = load_startup_config()
    setup_logging(config_data)

    detected_decoder_port, detected_nes_port = _detect_keyword_ports()
    parser = argparse.ArgumentParser(description="BCI 硬件控制系统")
    default_com = str(config_data.get("NES_port") or "").strip() or AppConfig.com_port
    if detected_decoder_port and detected_nes_port:
        default_com = detected_nes_port
        config_data["NES_port"] = detected_nes_port
        config_data["decoder_port"] = detected_decoder_port
        logger.info("自动检测串口成功: 脑机设备=%s, 神经肌肉电刺激设备=%s", detected_decoder_port, detected_nes_port)
    parser.add_argument("--com", dest="com_port", default=default_com, help="串口号（神经肌肉电刺激），默认从 config.json 的 NES_port 读取")
    parser.add_argument("--ws", dest="ws_url", default=AppConfig.ws_url, help="WebSocket 地址")
    parser.add_argument(
        "--log-recv",
        dest="log_receive_enabled",
        action="store_true",
        default=bool(config_data.get("log_receive_enabled", AppConfig.log_receive_enabled)),
        help="启用串口接收日志（解包前原始数据，默认开启）",
    )
    parser.add_argument("--no-log-recv", dest="log_receive_enabled", action="store_false", help="关闭串口接收日志")
    parser.add_argument(
        "--log-heartbeat",
        dest="log_heartbeat_enabled",
        action="store_true",
        default=bool(config_data.get("log_heartbeat_enabled", AppConfig.log_heartbeat_enabled)),
        help="启用下位机心跳帧日志",
    )
    parser.add_argument("--no-log-heartbeat", dest="log_heartbeat_enabled", action="store_false", help="关闭下位机心跳帧日志")
    parser.add_argument(
        "--ws-heartbeat",
        dest="ws_enable_heartbeat",
        action="store_true",
        help="启用 WebSocket 心跳",
    )
    parser.add_argument(
        "--ws-max-size",
        dest="ws_max_message_size",
        type=int,
        help="WebSocket 单帧最大字节数（<=0 表示不限制）",
    )
    parser.add_argument(
        "--disable-sub-window",
        dest="enable_sub_window",
        action="store_false",
        help="禁用副屏显示",
    )
    parser.add_argument(
        "--swap-screens",
        dest="swap_screens",
        action="store_true",
        help="交换主副屏显示",
    )
    parser.add_argument(
        "--paradigm-exe",
        dest="paradigm_exe_path",
        help="范式程序路径（ParadigmOne.exe）",
    )
    parser.add_argument(
        "--no-console",
        dest="hide_subprocess_console",
        action="store_true",
        help="打包后不显示主控/解码器/范式等子进程的终端窗口（Windows 下生效）",
    )
    parser.set_defaults(enable_sub_window=AppConfig.enable_sub_window)
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    apply_application_icon(app)
    load_resources()

    websocket_exe_path = str(config_data.get("websocket_exe") or "").strip() or None
    hide_console = getattr(args, "hide_subprocess_console", False)
    ws_server_process = start_websocket_server(websocket_exe_path, hide_console=hide_console)

    decoder_port = str(config_data.get("decoder_port") or "").strip() or None
    decoder_exe_path = str(config_data.get("decoder_exe") or "").strip() or None
    ws_max_message_size = config_data.get("ws_max_message_size", AppConfig.ws_max_message_size)
    if args.ws_max_message_size is not None:
        ws_max_message_size = args.ws_max_message_size
    if ws_max_message_size is not None:
        ws_max_message_size = int(ws_max_message_size)
        if ws_max_message_size <= 0:
            ws_max_message_size = None
    logger.info("decoder_exe=%s decoder_port=%s", decoder_exe_path, decoder_port)

    # 组合根：在入口统一装配依赖（UI -> 应用层 -> 服务层 -> 基础设施）
    config = AppConfig(
        com_port=args.com_port,
        ws_url=args.ws_url,
        log_receive_enabled=args.log_receive_enabled,
        log_heartbeat_enabled=args.log_heartbeat_enabled,
        ws_enable_heartbeat=args.ws_enable_heartbeat,
        ws_max_message_size=ws_max_message_size,
        enable_sub_window=args.enable_sub_window,
        swap_screens=args.swap_screens,
        paradigm_exe_path=args.paradigm_exe_path,
        decoder_port=decoder_port,
        decoder_exe_path=decoder_exe_path,
        hide_subprocess_console=getattr(args, "hide_subprocess_console", False),
    )
    services = build_services(config)

    decoder_manager = DecoderProcessManager(
        exe_path=config.decoder_exe_path,
        port=config.decoder_port,
        hide_console=config.hide_subprocess_console,
    )

    apps = build_apps(services, decoder_manager)

    # 启动解码器
    apps.decoder_app.start()
    connect_shutdown(app, services, apps.decoder_app, ws_server_process=ws_server_process)

    # 说明：范式动作指令/decoder.ready/system.ping 的处理已迁到 WsMessageRouter（service 层）
    run_login_flow(
        apps,
        services,
        enable_sub_window=config.enable_sub_window,
        swap_screens=config.swap_screens,
        paradigm_exe_path=config.paradigm_exe_path,
        decoder_port=config.decoder_port,
        hide_subprocess_console=config.hide_subprocess_console,
    )
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
