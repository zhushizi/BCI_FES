from __future__ import annotations

import logging
import struct
import sys
from array import array
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class EegHeader:
    timestamp: float
    n_chan: int
    n_samples: int
    n_power: int

    @property
    def eeg_size(self) -> int:
        return int(self.n_chan) * int(self.n_samples) * 8

    @property
    def power_size(self) -> int:
        return int(self.n_power) * 8

    @property
    def header_size(self) -> int:
        return 8 + 1 + 1 + 1

    @property
    def expected_total_size(self) -> int:
        return self.header_size + self.eeg_size + self.power_size


class EegBinaryParser:
    """EEG 二进制帧解析器（只负责解析，不处理业务）。"""

    HEADER_FORMAT = "<dBBB"
    HEADER_SIZE = 11

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def parse(self, bytes_data: bytes) -> Optional[dict[str, Any]]:
        if len(bytes_data) < self.HEADER_SIZE:
            self.logger.warning("EEG 数据包太短，无法解析头部")
            return None
        try:
            timestamp, n_chan, n_samples, n_power = struct.unpack(
                self.HEADER_FORMAT, bytes_data[:self.HEADER_SIZE]
            )
        except Exception as exc:
            self.logger.warning("EEG 头部解析失败: %s", exc)
            return None

        header = EegHeader(
            timestamp=float(timestamp),
            n_chan=int(n_chan),
            n_samples=int(n_samples),
            n_power=int(n_power),
        )
        if len(bytes_data) != header.expected_total_size:
            self.logger.warning("EEG 数据长度不匹配: 期望 %s, 实际 %s", header.expected_total_size, len(bytes_data))
            return None

        eeg_start = header.header_size
        eeg_end = eeg_start + header.eeg_size
        try:
            eeg_flat = array("d")
            eeg_flat.frombytes(bytes_data[eeg_start:eeg_end])
            if sys.byteorder != "little":
                eeg_flat.byteswap()
            if len(eeg_flat) != int(header.n_chan) * int(header.n_samples):
                self.logger.warning("EEG 数据长度与头部不一致")
                return None
            eeg_data = []
            for i in range(int(header.n_chan)):
                start = i * int(header.n_samples)
                end = start + int(header.n_samples)
                eeg_data.append(list(eeg_flat[start:end]))

            power_arr = array("d")
            power_arr.frombytes(bytes_data[eeg_end:])
            if sys.byteorder != "little":
                power_arr.byteswap()
            power_data = list(power_arr)
        except Exception as exc:
            self.logger.warning("EEG 数据解析失败: %s", exc)
            return None

        return {
            "timestamp": float(header.timestamp),
            "n_chan": int(header.n_chan),
            "n_samples": int(header.n_samples),
            "n_power": int(header.n_power),
            "eeg_data": eeg_data,
            "power_data": power_data,
        }
