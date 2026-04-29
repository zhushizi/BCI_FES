from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Optional


class DecoderProcessManager:
    """解码器进程管理：启动 / 停止 / 重启。"""

    def __init__(
        self,
        exe_path: Optional[str],
        port: Optional[str],
        baudrate: int = 115200,
        logger: Optional[logging.Logger] = None,
        hide_console: bool = False,
    ) -> None:
        self._exe_path = str(exe_path or "").strip() or None
        self._port = str(port or "").strip() or None
        self._baudrate = int(baudrate)
        self._logger = logger or logging.getLogger(__name__)
        self._process: Optional[subprocess.Popen] = None
        self._hide_console = bool(hide_console)

    @property
    def port(self) -> Optional[str]:
        return self._port

    def start(self) -> bool:
        exe_path = self._exe_path
        if not exe_path:
            self._logger.warning("未配置 decoder_exe，解码器不启动")
            return False
        if not os.path.isfile(exe_path):
            self._logger.error("解码器程序不存在: %s", exe_path)
            return False
        if self._process and self._process.poll() is None:
            return True

        if not self._port:
            self._logger.warning("未配置 decoder_port，解码器不启动")
            return False

        args = [
            exe_path,
            "-t",
            "1",
            "-c",
            str(self._port),
            "-p",
            str(self._baudrate),
        ]
        try:
            if os.name == "nt" and self._hide_console:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            else:
                creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
            self._process = subprocess.Popen(
                args,
                cwd=os.path.dirname(exe_path),
                creationflags=creationflags,
            )
            time.sleep(0.2)
            if self._process.poll() is not None:
                self._logger.error("解码器启动后立即退出，exit_code=%s", self._process.returncode)
                return False
            self._logger.info("解码器已启动: %s", " ".join(args))
            return True
        except Exception as exc:
            self._logger.error("启动解码器失败: %s", exc)
            return False

    def stop(self) -> None:
        if not self._process:
            return
        if self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
                self._logger.info("解码器已停止")
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None

    def restart(self, port: Optional[str]) -> bool:
        next_port = str(port or "").strip() or None
        if next_port and next_port == self._port and self._process and self._process.poll() is None:
            return True
        self._port = next_port
        self.stop()
        return self.start()
