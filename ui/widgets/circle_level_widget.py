"""
圆环等级滑块控件：可显示/可拖动圆环，中心显示当前等级（如 5 级）。
支持只读模式：仅显示、与 label 联动，不可拖动。
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import QWidget


class CircleLevelWidget(QWidget):
    """圆环等级控件：浅灰轨道、蓝色进度弧、末端手柄，中心「N级」。可设只读（不可调）。"""

    levelChanged = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min_level = 0
        self._max_level = 99
        self._level = 0
        self._dragging = False
        self._read_only = False

        self._track_color = QColor(0xE0, 0xE0, 0xE0)
        self._arc_color = QColor(88, 122, 244)   # 轨道蓝色
        self._handle_color = QColor(88, 122, 244)  # 摇杆蓝色
        self._handle_highlight = QColor(255, 255, 255)  # 摇杆内圆纯白
        self._bg_color = QColor(255, 255, 255)
        self._text_color = QColor(88, 122, 244)

        self.setMinimumSize(120, 120)
        self.setMouseTracking(False)

    def level(self) -> int:
        return self._level

    def set_level(self, value: int) -> None:
        v = max(self._min_level, min(self._max_level, int(value)))
        if v != self._level:
            self._level = v
            self.update()
            self.levelChanged.emit(self._level)

    def set_level_range(self, min_level: int, max_level: int) -> None:
        self._min_level = max(0, int(min_level))
        self._max_level = max(self._min_level, int(max_level))
        self._level = max(self._min_level, min(self._max_level, self._level))
        self.update()

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = bool(read_only)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, read_only)

    def is_read_only(self) -> bool:
        return self._read_only

    def _angle_for_level(self, level: int) -> float:
        if self._max_level <= self._min_level:
            return 0.0
        t = (level - self._min_level) / (self._max_level - self._min_level)
        return t * 360.0

    def _level_from_angle(self, angle_deg: float) -> int:
        a = angle_deg % 360.0
        if self._max_level <= self._min_level:
            return self._min_level
        t = a / 360.0
        idx = t * (self._max_level - self._min_level + 1)
        idx = max(0, min(self._max_level - self._min_level, idx))
        return self._min_level + int(round(idx))

    def _center_rect(self) -> QRectF:
        r = self.rect()
        side = min(r.width(), r.height())
        cx = r.x() + r.width() / 2
        cy = r.y() + r.height() / 2
        return QRectF(cx - side / 2, cy - side / 2, side, side)

    def _handle_radius_px(self) -> float:
        return 20.0

    def _handle_inner_radius_ratio(self) -> float:
        """摇杆内圆半径 / 外圆半径，调小则内圆直径变小，调大则变大。内圆直径 = 2 × 外圆半径 × 此值。"""
        return 0.5

    def _track_width(self) -> float:
        return 20.0

    def _track_outer_diameter(self) -> float:
        """灰色圆环外径（px）。"""
        return 291.0

    def _angle_to_point(self, cx: float, cy: float, radius: float, angle_deg: float) -> QPointF:
        rad = math.radians(-angle_deg + 90)
        return QPointF(cx + radius * math.cos(rad), cy - radius * math.sin(rad))

    def _point_to_angle(self, cx: float, cy: float, x: float, y: float) -> float:
        dx = x - cx
        dy = cy - y
        a = math.degrees(math.atan2(dx, dy))
        if a < 0:
            a += 360.0
        return a

    def _hit_handle(self, cx: float, cy: float, radius: float, x: float, y: float) -> bool:
        p = self._angle_to_point(cx, cy, radius, self._angle_for_level(self._level))
        d = math.hypot(x - p.x(), y - p.y())
        return d <= self._handle_radius_px() + 4

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        # 灰色圆环外径 291px，由外径反算中线半径与内半径
        outer_r = self._track_outer_diameter() / 2
        radius_mid = outer_r - self._track_width() / 2
        radius = outer_r - self._track_width()

        painter.fillRect(self.rect(), self._bg_color)

        track_rect = QRectF(
            cx - radius_mid,
            cy - radius_mid,
            radius_mid * 2,
            radius_mid * 2,
        )
        pen_track = QPen(self._track_color, self._track_width(), Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(track_rect)

        angle_deg = self._angle_for_level(self._level)
        pen_arc = QPen(self._arc_color, self._track_width() + 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(track_rect, 90 * 16, -int(angle_deg * 16))

        # 末端圆点：圆心在轨道环中线（大圆小圆半径平均值）
        handle_pos = self._angle_to_point(cx, cy, radius_mid, angle_deg)
        hr = self._handle_radius_px()
        inner_hr = hr * self._handle_inner_radius_ratio()  # 摇杆内圆半径
        handle_rect = QRectF(handle_pos.x() - hr, handle_pos.y() - hr, hr * 2, hr * 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._handle_color))
        painter.drawEllipse(handle_rect)
        painter.setBrush(QBrush(self._handle_highlight))
        painter.drawEllipse(QRectF(handle_pos.x() - inner_hr, handle_pos.y() - inner_hr, inner_hr * 2, inner_hr * 2))

        text = f"{self._level}级"
        font = QFont(self.font())
        font.setPointSize(max(14, min(24, int(self._track_outer_diameter() / 8))))
        painter.setFont(font)
        painter.setPen(self._text_color)
        painter.drawText(
            QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
            Qt.AlignCenter,
            text,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._read_only:
            return
        if event.button() != Qt.LeftButton:
            return
        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        outer_r = self._track_outer_diameter() / 2
        radius_mid = outer_r - self._track_width() / 2

        if self._hit_handle(cx, cy, radius_mid, event.position().x(), event.position().y()):
            self._dragging = True
            return
        dx = event.position().x() - cx
        dy = event.position().y() - cy
        d = math.hypot(dx, dy)
        if abs(d - radius_mid) <= self._track_width() + 8:
            self.set_level(self._level_from_angle(self._point_to_angle(cx, cy, event.position().x(), event.position().y())))
            self._dragging = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._read_only:
            return
        if not self._dragging:
            return
        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        angle = self._point_to_angle(cx, cy, event.position().x(), event.position().y())
        self.set_level(self._level_from_angle(angle))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
