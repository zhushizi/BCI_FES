"""
统一日志配置：从 config 读取，控制各模块是否打印及级别。

配置格式（config.json 中 "logging" 段）：
{
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "loggers": {
      "infrastructure.hardware.serial_hardware": "INFO",
      "service.business.ws": "WARNING",
      "service.business.session": "off"
    }
  }
}

- level: 根日志级别，可选 DEBUG / INFO / WARNING / ERROR / CRITICAL
- format: 可选，日志格式
- loggers: 可选，按 logger 名（或包名）设置级别；值为 "off" / "disabled" / "none" 时关闭该 logger 输出
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

# 字符串 -> logging 级别
_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

# 关闭输出：设为 CRITICAL 且不传播（或仅设 CRITICAL，子 logger 仍会继承根 handler）
_OFF_ALIASES = ("off", "disabled", "none", "false", "0")


def _parse_level(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _LEVEL_MAP:
            return _LEVEL_MAP[key]
        if key in _OFF_ALIASES:
            return logging.CRITICAL  # 实际“关闭”用 CRITICAL，不输出 INFO/WARNING 等
    return logging.INFO


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """
    根据 config 统一配置日志。应在程序入口尽早调用。

    Args:
        config: 完整配置字典；若为 None 或缺少 "logging"，则使用默认（INFO + 终端）。
    """
    if config is None:
        config = {}
    log_cfg = config.get("logging")
    if not isinstance(log_cfg, dict):
        log_cfg = {}

    level = _parse_level(log_cfg.get("level", "INFO"))
    fmt = log_cfg.get("format") or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loggers_cfg = log_cfg.get("loggers")
    if not isinstance(loggers_cfg, dict):
        loggers_cfg = {}

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（多次调用 setup_logging 时）
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(handler)

    for name, value in loggers_cfg.items():
        if not name or not isinstance(value, (str, int)):
            continue
        logger = logging.getLogger(name.strip())
        lv = _parse_level(value)
        logger.setLevel(lv)


def get_logger_choices_help() -> str:
    """返回常用 logger 名称说明，便于在 config 中配置。"""
    return """
常用 logger 名称（对应各模块 __name__，可做前缀匹配）：
  main
  infrastructure.hardware.serial_hardware   # 串口收发
  infrastructure.communication.websocket_service
  infrastructure.decoder.decoder_manager
  infrastructure.data.database_connection
  service.business.ws                       # WS 路由与 handlers
  service.business.session                  # 会话与 PatientTreatSession
  service.business.hardware                 # 心跳、刺激
  service.business.diagnostics.impedance_test_service
  service.user                              # 用户、患者、报告等
  application.session_app
  application.training_main_app
  ui.main_window
  ui.treat_modules
"""
