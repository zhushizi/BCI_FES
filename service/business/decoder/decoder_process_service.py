from __future__ import annotations

from typing import Optional

from infrastructure.decoder.decoder_manager import DecoderProcessManager


class DecoderProcessService:
    """解码器进程服务（服务层）。"""

    def __init__(self, decoder_manager: DecoderProcessManager) -> None:
        self._decoder_manager = decoder_manager

    def start(self) -> bool:
        return self._decoder_manager.start()

    def stop(self) -> None:
        self._decoder_manager.stop()

    def restart(self, port: Optional[str]) -> bool:
        return self._decoder_manager.restart(port)

    def get_port(self) -> Optional[str]:
        return self._decoder_manager.port
