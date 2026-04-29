from __future__ import annotations
'''
设置页（tabWidget 的 tab4）管理
'''
import logging
import ctypes
from typing import Optional

from PySide6.QtWidgets import QWidget

from ui.core.utils import get_ui_attr, safe_connect


class SetPageController:
    """设置页（tabWidget 的 tab4）管理"""

    def __init__(
        self,
        parent: QWidget,
        ui,
        logger: Optional[logging.Logger] = None,
        decoder_port: Optional[str] = None,
        hardware_config_app=None,
    ):
        self.parent = parent
        self.ui = ui
        self.logger = logger or logging.getLogger(__name__)
        self.decoder_port = str(decoder_port or "").strip() or None
        self.nes_port = None
        self.hardware_config_app = hardware_config_app
        self._endpoint_volume = None
        self._muted = False
        self._volume_before_mute = None
        self._init_audio_endpoint()

    def bind_signals(self):
        combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        safe_connect(self.logger, getattr(combo, "currentIndexChanged", None), self._on_decoder_port_changed)
        nes_combo = get_ui_attr(self.ui, "comboBox_NES_port")
        safe_connect(self.logger, getattr(nes_combo, "currentIndexChanged", None), self._on_nes_port_changed)
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if slider is None:
            self.logger.warning("未找到音量滑条: horizontalSlider_volume")
        safe_connect(self.logger, getattr(slider, "valueChanged", None), self._on_volume_changed)
        btn_minus = get_ui_attr(self.ui, "pushButton_vol_minus")
        if btn_minus is None:
            self.logger.warning("未找到音量减按钮: pushButton_vol_minus")
        safe_connect(self.logger, getattr(btn_minus, "clicked", None), self._on_volume_minus)
        btn_add = get_ui_attr(self.ui, "pushButton_vol_add")
        if btn_add is None:
            self.logger.warning("未找到音量加按钮: pushButton_vol_add")
        safe_connect(self.logger, getattr(btn_add, "clicked", None), self._on_volume_add)
        btn_toggle = get_ui_attr(self.ui, "pushButton_vol_shutopen")
        if btn_toggle is None:
            self.logger.warning("未找到静音按钮: pushButton_vol_shutopen")
        safe_connect(self.logger, getattr(btn_toggle, "clicked", None), self._on_volume_toggle)

    def init_ui(self):
        if self.hardware_config_app:
            self.decoder_port = self.hardware_config_app.get_decoder_port() or self.decoder_port
            self.nes_port = self.hardware_config_app.get_nes_port()
        port_details = self._list_available_port_details()
        detected = self._classify_ports(port_details)
        auto_decoder = detected.get("decoder_port")
        auto_nes = detected.get("NES_port")

        # 若同时检测到两类设备，自动应用映射并连接
        if self.hardware_config_app and auto_decoder and auto_nes:
            if auto_decoder != self.decoder_port:
                if self.hardware_config_app.set_decoder_port(auto_decoder):
                    self.decoder_port = auto_decoder
            if auto_nes != self.nes_port:
                if self.hardware_config_app.set_nes_port(auto_nes):
                    self.nes_port = auto_nes

        combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        if combo:
            prev_block = combo.blockSignals(True)
            combo.clear()
            options = self._build_port_options(port_details=port_details, preferred_port=self.decoder_port, role="decoder")
            for display, port in options:
                combo.addItem(display, port)
            if self.decoder_port:
                self._set_combo_by_port(combo, self.decoder_port)
            combo.blockSignals(prev_block)

        nes_combo = get_ui_attr(self.ui, "comboBox_NES_port")
        if nes_combo:
            prev_block = nes_combo.blockSignals(True)
            nes_combo.clear()
            options = self._build_port_options(port_details=port_details, preferred_port=self.nes_port, role="nes")
            for display, port in options:
                nes_combo.addItem(display, port)
            if self.nes_port:
                self._set_combo_by_port(nes_combo, self.nes_port)
            nes_combo.blockSignals(prev_block)
        self._init_volume_controls()

    def refresh(self):
        pass

    def _init_volume_controls(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        try:
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setSingleStep(5)
            slider.setPageStep(10)
            slider.setTracking(True)
        except Exception:
            pass
        current = self._get_system_volume_percent()
        if current is not None:
            prev = slider.blockSignals(True)
            slider.setValue(current)
            slider.blockSignals(prev)
            self._muted = current == 0
            if not self._muted:
                self._volume_before_mute = current
        else:
            self.logger.warning("未能读取系统音量，滑条保持默认值")
        self._sync_volume_icon()

    def _init_audio_endpoint(self) -> None:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        self._ensure_audio_endpoint()

    def _ensure_audio_endpoint(self) -> bool:
        if self._endpoint_volume is not None:
            return True
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            device = AudioUtilities.GetSpeakers()
            if hasattr(device, "Activate"):
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            else:
                interface = device._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint_volume = interface.QueryInterface(IAudioEndpointVolume)
            return True
        except Exception as exc:
            self.logger.warning("初始化系统音量接口失败: %s", exc)
            return False

    def _get_system_volume_percent(self) -> int | None:
        try:
            if self._ensure_audio_endpoint():
                scalar = self._endpoint_volume.GetMasterVolumeLevelScalar()
                return int(round(float(scalar) * 100))
        except Exception as exc:
            self.logger.warning("读取系统音量失败: %s", exc)
        try:
            winmm = ctypes.windll.winmm
            vol = ctypes.c_uint()
            res = winmm.waveOutGetVolume(0, ctypes.byref(vol))
            if res != 0:
                return None
            left = vol.value & 0xFFFF
            right = (vol.value >> 16) & 0xFFFF
            avg = (left + right) / 2.0
            return int(round(avg / 0xFFFF * 100))
        except Exception:
            return None

    def _set_system_volume_percent(self, value: int) -> bool:
        try:
            if self._ensure_audio_endpoint():
                pct = max(0, min(100, int(value)))
                self._endpoint_volume.SetMasterVolumeLevelScalar(pct / 100.0, None)
                return True
        except Exception as exc:
            self.logger.warning("设置系统音量失败(CoreAudio): %s", exc)
        try:
            winmm = ctypes.windll.winmm
            pct = max(0, min(100, int(value)))
            vol = int(pct / 100 * 0xFFFF)
            winmm.waveOutSetVolume(0, vol | (vol << 16))
            return True
        except Exception as exc:
            self.logger.debug("设置系统音量失败: %s", exc)
        return False

    def _on_volume_changed(self, value: int) -> None:
        ok = self._set_system_volume_percent(value)
        if not ok:
            self.logger.warning("设置系统音量失败，目标值: %s", value)
            return
        current = self._get_system_volume_percent()
        if current is not None and abs(current - int(value)) >= 3:
            self.logger.warning("系统音量未同步，目标=%s 实际=%s", value, current)
        self._muted = int(value) == 0
        if not self._muted:
            self._volume_before_mute = int(value)
        self._sync_volume_icon()

    def _set_volume_slider(self, value: int) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        prev = slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(prev)

    def _sync_volume_icon(self) -> None:
        btn = get_ui_attr(self.ui, "pushButton_vol_shutopen")
        if not btn:
            return
        if self._muted:
            btn.setStyleSheet("border-image: url(:/set/pic/set_volumeopen.png);")
        else:
            btn.setStyleSheet("border-image: url(:/set/pic/set_volumeshut.png);")

    def _on_volume_toggle(self) -> None:
        if not self._muted:
            current = self._get_system_volume_percent()
            if current is not None:
                self._volume_before_mute = current
            self._set_system_volume_percent(0)
            self._set_volume_slider(0)
            self._muted = True
        else:
            restore = self._volume_before_mute if self._volume_before_mute is not None else 50
            self._set_system_volume_percent(restore)
            self._set_volume_slider(restore)
            self._muted = False
        self._sync_volume_icon()

    def _on_volume_add(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        step = slider.singleStep() or 5
        slider.setValue(min(slider.maximum(), slider.value() + step))

    def _on_volume_minus(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        step = slider.singleStep() or 5
        slider.setValue(max(slider.minimum(), slider.value() - step))

    def _on_decoder_port_changed(self, _index: int) -> None:
        combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        next_port = self._get_selected_port(combo)
        if not next_port:
            return
        if self.decoder_port == next_port:
            return
        self.decoder_port = next_port
        if self.hardware_config_app:
            ok = self.hardware_config_app.set_decoder_port(next_port)
            if not ok:
                self.logger.warning("切换解码器端口失败: %s", next_port)

    def _on_nes_port_changed(self, _index: int) -> None:
        combo = get_ui_attr(self.ui, "comboBox_NES_port")
        next_port = self._get_selected_port(combo)
        if not next_port:
            return
        if self.nes_port == next_port:
            return
        self.nes_port = next_port
        if self.hardware_config_app:
            ok = self.hardware_config_app.set_nes_port(next_port)
            if not ok:
                self.logger.warning("切换串口失败: %s", next_port)

    def _list_available_ports(self) -> list[str]:
        if not self.hardware_config_app:
            self.logger.warning("hardware_config_app 未注入，无法读取串口列表")
            return []
        try:
            return list(self.hardware_config_app.list_available_ports())
        except Exception:
            return []

    def _list_available_port_details(self) -> list[dict[str, str]]:
        if not self.hardware_config_app:
            return []
        try:
            return list(self.hardware_config_app.list_available_port_details())
        except Exception:
            return []

    def _classify_ports(self, port_details: list[dict[str, str]]) -> dict[str, Optional[str]]:
        if not self.hardware_config_app:
            return {"decoder_port": None, "NES_port": None}
        try:
            return self.hardware_config_app.classify_ports(port_details)
        except Exception:
            return {"decoder_port": None, "NES_port": None}

    def _build_port_options(
        self,
        *,
        port_details: list[dict[str, str]],
        preferred_port: Optional[str],
        role: str,
    ) -> list[tuple[str, str]]:
        detected = self._classify_ports(port_details)
        decoder_port = detected.get("decoder_port")
        nes_port = detected.get("NES_port")
        options: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in port_details:
            device = str(item.get("device") or "").strip()
            if not device or device in seen:
                continue
            seen.add(device)
            if role == "decoder" and device == decoder_port:
                options.append((f"脑机设备 ({device})", device))
            elif role == "nes" and device == nes_port:
                options.append((f"神经肌肉电刺激设备 ({device})", device))
            else:
                options.append((device, device))
        p = str(preferred_port or "").strip()
        if p and p not in seen:
            options.insert(0, (p, p))
        return options

    def _set_combo_by_port(self, combo, port: str) -> None:
        target = str(port or "").strip()
        if not combo or not target:
            return
        for i in range(combo.count()):
            if str(combo.itemData(i) or "").strip() == target:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentText(target)

    def _get_selected_port(self, combo) -> str:
        if combo is None:
            return ""
        data = combo.currentData()
        if data:
            return str(data).strip()
        return str(combo.currentText() or "").strip()
