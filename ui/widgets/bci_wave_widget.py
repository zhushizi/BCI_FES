from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QWidget


class BCIWaveWidget(QWidget):
    """
    简易 EEG 波形显示控件（多通道叠加分区显示）。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)
        self._eeg_data: Any = None
        self._timestamp: float | None = None
        self._prev_timestamp: float | None = None
        self._buffers: list[list[float]] = []
        self._sample_interval: float | None = None
        self._window_sec = 10.0
        self._max_points = 800
        self._bg_color = QColor(10, 10, 10)
        self._grid_color = QColor(40, 40, 40)
        self._wave_color = QColor(0, 200, 255)
        self._label_color = QColor(220, 220, 220)
        self._draw_labels = True
        # 由 decoder.ImpedanceValue 的 electrode 经 set_channel_labels 写入；未收到前为空
        self._channel_labels: list[str] = []
        # 与最近一次已绘制可见通道数对齐侧栏行数（通道数可多于阻抗 electrode 列表）
        self._last_visible_channel_count: int = 0
        # 最近一次绘制时的原始 EEG 通道数（与侧栏行数对齐用）
        self._last_raw_channel_count: int = 0

    def count_visible_eeg_rows(self, eeg_data: Any) -> int:
        """与 _filter_channels 一致的可视行数（排除 CH 前缀通道），用于侧栏布局。"""
        eeg = self._to_2d_array(eeg_data)
        if not eeg:
            return self._last_visible_channel_count
        return sum(1 for idx in range(len(eeg)) if not self._channel_row_hidden_for_display(idx))

    def set_channel_labels(self, electrodes: Iterable[Any]) -> None:
        """由 decoder.ImpedanceValue 的 electrode 列表设置通道名，顺序与 EEG 通道一致。"""
        labels: list[str] = []
        for x in electrodes:
            s = str(x or "").strip()
            if not s or s.upper() == "NONE":
                labels.append("")
            else:
                labels.append(s)
        self._channel_labels = labels
        self._last_raw_channel_count = 0
        self._last_visible_channel_count = 0
        self.update()

    def update_eeg(self, eeg_data: Any, timestamp: Optional[float] = None) -> None:
        self._append_frame(eeg_data, timestamp=timestamp)
        self.update()

    def set_draw_labels(self, enabled: bool) -> None:
        self._draw_labels = bool(enabled)
        self.update()

    def get_visible_labels(self) -> list[str]:
        n = max(len(self._channel_labels), self._last_raw_channel_count)
        if n <= 0:
            n = 1
        out: list[str] = []
        for idx in range(n):
            if self._channel_row_hidden_for_display(idx):
                continue
            label = self._channel_label_at(idx)
            out.append(label)
        return out

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, self._bg_color)

        if self._eeg_data is None:
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawText(rect, Qt.AlignCenter, "暂无波形数据")
            return

        eeg = self._to_2d_array(self._eeg_data)
        if eeg is None:
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawText(rect, Qt.AlignCenter, "波形格式不支持")
            return

        self._last_raw_channel_count = len(eeg)
        visible_eeg, visible_labels = self._filter_channels(eeg)
        n_chan = len(visible_eeg)
        if n_chan <= 0:
            return
        self._last_visible_channel_count = n_chan

        width = rect.width()
        height = rect.height()
        channel_height = height / n_chan

        painter.setPen(QPen(self._grid_color, 1))
        for i in range(1, n_chan):
            y = int(i * channel_height)
            painter.drawLine(0, y, width, y)

        painter.setPen(QPen(self._wave_color, 1))
        for idx, samples in enumerate(visible_eeg):
            if not samples:
                continue
            data = self._downsample(samples, self._max_points)
            max_abs = max((abs(v) for v in data), default=1.0)
            if max_abs == 0:
                max_abs = 1.0

            y_offset = (idx + 0.5) * channel_height
            y_scale = channel_height * 0.4 / max_abs
            x_step = width / max(len(data) - 1, 1)

            label = visible_labels[idx] if idx < len(visible_labels) else ""
            if self._draw_labels and label:
                painter.setPen(self._label_color)
                painter.drawText(6, int(y_offset - channel_height * 0.3), label)

            painter.setPen(QPen(self._wave_color, 1))
            poly = QPolygonF()
            for i, v in enumerate(data):
                x = i * x_step
                y = y_offset - v * y_scale
                poly.append(QPointF(x, y))
            painter.drawPolyline(poly)

    def _downsample(self, samples: list[float], max_points: int) -> list[float]:
        if len(samples) <= max_points:
            return samples
        step = max(int(len(samples) / max_points), 1)
        return samples[::step]

    def _append_frame(self, eeg_data: Any, timestamp: Optional[float]) -> None:
        eeg = self._to_2d_array(eeg_data)
        if eeg is None:
            self._eeg_data = None
            return

        n_chan = len(eeg)
        if n_chan <= 0:
            return

        if not self._buffers or len(self._buffers) != n_chan:
            self._buffers = [[] for _ in range(n_chan)]

        n_samples = len(eeg[0]) if eeg[0] else 0
        if timestamp is not None and n_samples > 0:
            if self._prev_timestamp is not None:
                delta = float(timestamp) - float(self._prev_timestamp)
                if delta > 0:
                    self._sample_interval = delta / float(n_samples)
            self._prev_timestamp = float(timestamp)

        for idx, samples in enumerate(eeg):
            if samples:
                self._buffers[idx].extend(samples)

        max_keep = self._get_max_keep()
        if max_keep > 0:
            for idx in range(n_chan):
                if len(self._buffers[idx]) > max_keep:
                    self._buffers[idx] = self._buffers[idx][-max_keep:]

        self._eeg_data = self._buffers
        self._timestamp = timestamp

    def _get_max_keep(self) -> int:
        if self._sample_interval and self._sample_interval > 0:
            return max(int(self._window_sec / self._sample_interval), 1)
        return self._max_points

    def _to_2d_array(self, eeg_data: Any) -> Optional[list[list[float]]]:
        if hasattr(eeg_data, "tolist") and hasattr(eeg_data, "shape"):
            try:
                data = eeg_data.tolist()
                if isinstance(data, list) and data and isinstance(data[0], list):
                    return [[float(v) for v in ch] for ch in data]
            except Exception:
                self._logger.exception("EEG 数据转换失败")

        if isinstance(eeg_data, list) and eeg_data:
            if all(isinstance(ch, list) for ch in eeg_data):
                return [[float(v) for v in ch] for ch in eeg_data]
        return None

    def _channel_label_at(self, idx: int) -> str:
        if idx < len(self._channel_labels):
            label = self._channel_labels[idx]
            if label.upper() == "NONE":
                return ""
            return label
        return ""

    @staticmethod
    def _is_ch_prefixed_electrode_label(label: str) -> bool:
        """阻抗/电极名以 CH 开头（不区分大小写）的通道在训练波形中不展示。"""
        s = (label or "").strip()
        if not s:
            return False
        return s.upper().startswith("CH")

    def _channel_row_hidden_for_display(self, idx: int) -> bool:
        return self._is_ch_prefixed_electrode_label(self._channel_label_at(idx))

    def _filter_channels(self, eeg: list[list[float]]) -> tuple[list[list[float]], list[str]]:
        visible_eeg: list[list[float]] = []
        visible_labels: list[str] = []
        for idx, samples in enumerate(eeg):
            if self._channel_row_hidden_for_display(idx):
                continue
            visible_eeg.append(samples)
            visible_labels.append(self._channel_label_at(idx))
        return visible_eeg, visible_labels
