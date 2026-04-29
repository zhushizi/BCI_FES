from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class PowerBarWidget(QWidget):
    """简易功率柱状图（固定三通道）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values = [0.0, 0.0, 0.0]
        self._labels = ["C3", "Cz", "C4"]
        self._base_max_value = 40.0
        self._max_value = self._base_max_value
        self._auto_scale = True
        self._tick_count = 4  # 0~40 -> 5 条水平线

        self._bg_color = QColor(255, 255, 255)
        self._grid_color = QColor(210, 225, 250)
        self._axis_color = QColor(190, 205, 235)
        self._label_color = QColor(90, 115, 175)
        self._axis_x_label_color = QColor(0x93, 0x93, 0x93)  # 横坐标（底部通道名）字体颜色
        self._value_color = QColor(90, 115, 175)
        self._bar_top_color = QColor(255, 255, 255)  # 纯白
        self._bar_bottom_color = QColor(120, 150, 255)
        self._bar_border_color = QColor(0x80, 0x92, 0xDB)  # 柱子边框
        self._bar_dot_line_color = QColor(0x80, 0x92, 0xDB)  # 柱头点线颜色（与边框一致）
        # 坐标轴标签用更大字号
        self._axis_font = QFont(self.font())
        self._axis_font.setPointSize(max(self._axis_font.pointSize() + 2, 11))

    def update_power(self, values: Iterable[float]) -> None:
        vals = [float(v) for v in values][:3]
        while len(vals) < 3:
            vals.append(0.0)
        self._values = vals
        max_val = max(max(abs(v) for v in vals), 1.0)
        if self._auto_scale:
            self._max_value = max(self._base_max_value, max_val)
        else:
            self._max_value = max(self._max_value, 1.0)
        self.update()

    def set_channel_labels(self, labels: Iterable[str]) -> None:
        vals = [str(v) for v in labels][:3]
        while len(vals) < 3:
            vals.append("")
        self._labels = vals
        self.update()

    def set_base_max(self, value: float) -> None:
        self._base_max_value = max(float(value), 1.0)
        if self._auto_scale:
            self._max_value = max(self._base_max_value, self._max_value)
        self.update()

    def set_auto_scale(self, enabled: bool) -> None:
        self._auto_scale = bool(enabled)
        self.update_power(self._values)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, self._bg_color)

        fm_axis = QFontMetrics(self._axis_font)
        fm = QFontMetrics(self.font())
        left_pad = max(36, fm_axis.horizontalAdvance("40") + 10)
        right_pad = 10
        top_pad = 10
        bottom_pad = max(26, fm_axis.ascent() + 10)
        chart = rect.adjusted(left_pad, top_pad, -right_pad, -bottom_pad)
        width = chart.width()
        height = chart.height()

        bar_width = max(int(width / 6), 18)
        gap = (width - bar_width * 3) / 4 if width > bar_width * 3 else 10
        bottom = chart.bottom()

        # 网格线
        grid_pen = QPen(self._grid_color, 1, Qt.DashLine)
        painter.setPen(grid_pen)
        for i in range(self._tick_count + 1):
            y = bottom - int(height * i / self._tick_count)
            painter.drawLine(chart.left(), y, chart.right(), y)

        # Y 轴刻度（使用更大字号）
        painter.setFont(self._axis_font)
        painter.setPen(QPen(self._label_color, 1))
        for i in range(self._tick_count + 1):
            value = (self._max_value / self._tick_count) * i
            text = f"{value:.0f}"
            text_w = fm_axis.horizontalAdvance(text)
            y = bottom - int(height * i / self._tick_count)
            painter.drawText(chart.left() - text_w - 6, y + fm_axis.ascent() // 2, text)

        for i, val in enumerate(self._values):
            bar_height = int((abs(val) / self._max_value) * (height * 0.85))
            x = int(chart.left() + gap + i * (bar_width + gap))
            y = bottom - bar_height
            grad = QLinearGradient(x, y, x, bottom)
            grad.setColorAt(0.0, self._bar_top_color)
            grad.setColorAt(1.0, self._bar_bottom_color)

            painter.setBrush(grad)
            painter.setPen(QPen(self._bar_border_color, 1))
            painter.drawRect(x, y, bar_width, bar_height)

            # 柱头点线：圆点 + 竖线 + 数值 + 水平虚线（仅当柱子有高度时绘制）
            if bar_height >= 2:
                cx = x + bar_width // 2
                line_height = 8
                dot_r = 3
                painter.setPen(Qt.NoPen)
                painter.setBrush(self._bar_dot_line_color)
                painter.drawEllipse(int(cx - dot_r), int(y - dot_r), dot_r * 2, dot_r * 2)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(self._bar_dot_line_color, 1))
                painter.drawLine(int(cx), int(y), int(cx), int(y - line_height))

                val_text = f"{val:.2f}"
                tw = fm.horizontalAdvance(val_text)
                val_y = y - line_height - 4
                painter.setFont(self.font())
                painter.setPen(self._value_color)
                painter.drawText(int(x + (bar_width - tw) / 2), int(val_y), val_text)
            else:
                painter.setFont(self.font())
                painter.setPen(self._value_color)
                val_text = f"{val:.2f}"
                painter.drawText(int(x + (bar_width - fm.horizontalAdvance(val_text)) / 2), int(y - 4), val_text)

            label = self._labels[i] if i < len(self._labels) else ""
            if label:
                painter.setFont(self._axis_font)
                label_w = fm_axis.horizontalAdvance(label)
                painter.setPen(self._axis_x_label_color)
                painter.drawText(x + (bar_width - label_w) / 2, bottom + fm_axis.ascent() + 4, label)
