"""
解码器应用层（Application Layer）
"""

from __future__ import annotations

import logging
from typing import Optional

from service.business.decoder.decoder_process_service import DecoderProcessService


class DecoderApp:
    """解码器应用层：UI 仅通过此类控制解码器进程。"""

    def __init__(self, decoder_service: DecoderProcessService):
        self.decoder_service = decoder_service
        self.logger = logging.getLogger(__name__)

    def start(self) -> bool:
        return self.decoder_service.start()

    def stop(self) -> None:
        self.decoder_service.stop()

    def restart(self, port: Optional[str]) -> bool:
        return self.decoder_service.restart(port)

    def get_port(self) -> Optional[str]:
        return self.decoder_service.get_port()
