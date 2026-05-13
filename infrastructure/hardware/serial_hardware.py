"""
串口通信类 - 负责与下位机通过串口进行数据交互
    提供串口通信能力
    管理连接和资源
    传输原始字节数据
"""

import serial
import serial.tools.list_ports
from typing import Optional, Callable
from threading import Thread
import logging

from service.business.protocol.heartbeat_frame import HeartbeatFrame


class SerialHardware:
    """串口硬件通信类"""

    # 与刺激协议设备字节一致；识别「第5字节为 FC」的治疗完成应答壳，避免被心跳日志策略误抑制
    _STIM_DEVICE_CODES = (0xEA, 0xEB, 0xFA, 0xFB)
    _STIM_FRAME_TYPE_TREAT_DONE = 0xFC

    def __init__(self, port: str = None, baudrate: int = 115200,
                 timeout: float = 1.0, bytesize: int = 8,
                 parity: str = 'N', stopbits: int = 1,
                 log_receive_enabled: bool = True,
                 log_heartbeat_enabled: bool = False,
                 leg_side_label: str = ""):
        """
        初始化串口通信
        
        Args:
            port: 串口名称，如 'COM3' 或 '/dev/ttyUSB0'，None 则自动检测
            baudrate: 波特率，默认 115200
            timeout: 超时时间（秒），默认 1.0
            bytesize: 数据位，默认 8
            parity: 校验位，'N'(无校验), 'E'(偶校验), 'O'(奇校验)
            stopbits: 停止位，1 或 2
            log_receive_enabled: 为 False 时不打印任何收发原始 hex；为 True 时打印一般数据，并对心跳/校时见下项
            log_heartbeat_enabled: 仅在 log_receive_enabled 为 True 时生效；为 True 时打印「下位机心跳帧」与「本机 CE 校时应答」，
                为 False 时不打印上述两类；**不会**抑制 55AA0D+EA/EB/FA/FB 且第5字节为 FC 的治疗完成应答等其它帧
            leg_side_label: 日志标注用，如「左」「右」；空则收发日志不区分侧别
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        
        self.leg_side_label = str(leg_side_label or "").strip()
        self.serial_obj: Optional[serial.Serial] = None
        self.is_connected_flag = False
        self.data_received_callback: Optional[Callable[[bytes], None]] = None
        self._data_received_callbacks: list[Callable[[bytes], None]] = []
        self.receive_thread: Optional[Thread] = None
        self.receive_running = False
        self.log_receive_enabled = bool(log_receive_enabled)
        self.log_heartbeat_enabled = bool(log_heartbeat_enabled)
        
        self.logger = logging.getLogger(__name__)

    def _log_side_prefix(self) -> str:
        return f"[{self.leg_side_label}] " if self.leg_side_label else ""

    @property
    def device_name(self) -> str:
        """设备名称"""
        return f"Serial-{self.port}" if self.port else "Serial-Unknown"
    
    def connect(self) -> bool:
        """
        连接串口设备
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 如果未指定端口，尝试自动检测
            if self.port is None:
                available_ports = self.list_available_ports()
                if not available_ports:
                    self.logger.error("未找到可用的串口设备")
                    return False
                self.port = available_ports[0].device
                self.logger.info(f"自动选择串口: {self.port}")
            
            # 创建串口对象
            self.serial_obj = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout
            )
            
            if self.serial_obj.is_open:
                self.is_connected_flag = True
                # 启动数据接收线程
                self._start_receive_thread()
                self.logger.info(f"串口连接成功: {self.port} @ {self.baudrate}bps")
                return True
            else:
                self.logger.error(f"串口打开失败: {self.port}")
                return False
                
        except serial.SerialException as e:
            self.logger.error(f"串口连接异常: {e}")
            self.is_connected_flag = False
            return False
        except Exception as e:
            self.logger.error(f"连接串口时发生未知错误: {e}")
            self.is_connected_flag = False
            return False
    
    def disconnect(self) -> None:
        """断开串口连接"""
        # 停止接收线程
        self._stop_receive_thread()
        
        # 关闭串口
        if self.serial_obj and self.serial_obj.is_open:
            try:
                self.serial_obj.close()
                self.logger.info(f"串口已断开: {self.port}")
            except Exception as e:
                self.logger.error(f"断开串口时发生错误: {e}")
        
        self.serial_obj = None
        self.is_connected_flag = False
    
    def is_connected(self) -> bool:
        """
        检查串口是否已连接
        
        Returns:
            bool: 连接状态
        """
        return self.is_connected_flag and self.serial_obj is not None and self.serial_obj.is_open
    
    def send_data(self, data: bytes) -> bool:
        """
        发送数据到下位机
        
        Args:
            data: 要发送的数据（字节流）
            
        Returns:
            bool: 发送是否成功
        """
        if not self.is_connected():
            self.logger.warning("串口未连接，无法发送数据")
            return False
        
        try:
            bytes_written = self.serial_obj.write(data)
            self.serial_obj.flush()  # 确保数据立即发送
            if self._should_log_data(data):
                self.logger.info(f"[发送指令] {self._log_side_prefix()}数据: {data.hex()} ({len(data)} 字节)")
            return bytes_written == len(data)
        except serial.SerialException as e:
            self.logger.error(f"发送数据失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"发送数据时发生未知错误: {e}")
            return False
    
    def read_data(self, size: int = 1024) -> Optional[bytes]:
        """
        从下位机读取数据（同步读取）
        
        Args:
            size: 要读取的数据大小（字节）
            
        Returns:
            Optional[bytes]: 读取到的数据，失败返回 None
        """
        if not self.is_connected():
            self.logger.warning("串口未连接，无法读取数据")
            return None
        
        try:
            if self.serial_obj.in_waiting > 0:
                data = self.serial_obj.read(min(size, self.serial_obj.in_waiting))
                if self._should_log_data(data):
                    # 使用 INFO 级别，确保在终端打印
                    self.logger.info(f"[接收指令] {self._log_side_prefix()}数据: {data.hex()} ({len(data)} 字节)")
                return data
            return b''
        except serial.SerialException as e:
            self.logger.error(f"读取数据失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"读取数据时发生未知错误: {e}")
            return None
    
    def set_data_received_callback(self, callback: Callable[[bytes], None]) -> None:
        """
        设置数据接收回调函数（用于异步接收）
        
        Args:
            callback: 数据接收回调函数，参数为接收到的数据
        """
        self.data_received_callback = callback
        self._data_received_callbacks = [callback] if callback else []

    def add_data_received_callback(self, callback: Callable[[bytes], None]) -> None:
        """
        追加数据接收回调函数（允许多个订阅者）

        Args:
            callback: 数据接收回调函数，参数为接收到的数据
        """
        if not callback:
            return
        if callback not in self._data_received_callbacks:
            self._data_received_callbacks.append(callback)
    
    def _start_receive_thread(self) -> None:
        """启动数据接收线程"""
        if self.receive_thread is None or not self.receive_thread.is_alive():
            self.receive_running = True
            self.receive_thread = Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            self.logger.debug("数据接收线程已启动")
    
    def _stop_receive_thread(self) -> None:
        """停止数据接收线程"""
        self.receive_running = False
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
            self.logger.debug("数据接收线程已停止")
    
    def _receive_loop(self) -> None:
        """数据接收循环（在独立线程中运行）"""
        while self.receive_running and self.is_connected():
            try:
                if self.serial_obj and self.serial_obj.in_waiting > 0:
                    data = self.serial_obj.read(self.serial_obj.in_waiting)
                    if data:
                        if self._should_log_data(data):
                            # 使用 INFO 级别，确保在终端打印接收到的数据
                            self.logger.info(f"[接收指令] {self._log_side_prefix()}数据: {data.hex()} ({len(data)} 字节)")
                        if self._data_received_callbacks:
                            for cb in list(self._data_received_callbacks):
                                try:
                                    cb(data)
                                except Exception as e:
                                    self.logger.error(f"数据接收回调执行失败: {e}")
                else:
                    # 避免CPU占用过高
                    import time
                    time.sleep(0.01)
            except serial.SerialException as e:
                self.logger.error(f"接收数据时发生错误: {e}")
                break
            except Exception as e:
                self.logger.error(f"接收数据时发生未知错误: {e}")
                break

    def _should_log_data(self, data: bytes) -> bool:
        """总开关 log_receive；log_heartbeat 仅作用于下位机心跳与本机 CE 校时应答；不屏蔽 FC 治疗应答壳。"""
        if not self.log_receive_enabled:
            return False
        if self._is_stim_shell_treat_done_fc(data):
            return True
        if self._is_uplink_timesync_ce_frame(data) or self._is_downlink_device_heartbeat_frame(data):
            return bool(self.log_heartbeat_enabled)
        return True

    def _is_stim_shell_treat_done_fc(self, data: bytes) -> bool:
        """55 AA 0D + EA/EB/FA/FB + 第5字节 FC（0-based 索引4），定长 13 字节。"""
        if len(data) != HeartbeatFrame.FRAME_SIZE:
            return False
        if data[0:2] != HeartbeatFrame.FRAME_HEADER or data[2] != HeartbeatFrame.FRAME_LENGTH:
            return False
        if data[3] not in self._STIM_DEVICE_CODES:
            return False
        return data[4] == self._STIM_FRAME_TYPE_TREAT_DONE

    def _is_uplink_timesync_ce_frame(self, data: bytes) -> bool:
        """本机发出的校时应答：55 AA 0D CE + CRC。"""
        if len(data) != HeartbeatFrame.FRAME_SIZE:
            return False
        if data[0:2] != HeartbeatFrame.FRAME_HEADER or data[2] != HeartbeatFrame.FRAME_LENGTH:
            return False
        if data[3] != HeartbeatFrame.SET_TIME_COMMAND:
            return False
        expected = HeartbeatFrame.calculate_crc16(bytearray(data[: HeartbeatFrame.FRAME_DATA_SIZE]))
        return data[HeartbeatFrame.FRAME_DATA_SIZE : HeartbeatFrame.FRAME_SIZE] == expected

    def _is_downlink_device_heartbeat_frame(self, data: bytes) -> bool:
        """下位机发来的心跳请求（E0/F0 侧 + 0xFB 标志等）。"""
        return HeartbeatFrame.is_heartbeat_request(data, self.logger)

    @staticmethod
    def list_available_ports() -> list:
        """
        列出所有可用的串口
        
        Returns:
            list: 可用串口列表
        """
        return list(serial.tools.list_ports.comports())

    @staticmethod
    def list_available_port_details() -> list[dict[str, str]]:
        """列出可用串口详情，包含 device/description/manufacturer/hwid。"""
        details: list[dict[str, str]] = []
        for p in SerialHardware.list_available_ports():
            details.append(
                {
                    "device": str(getattr(p, "device", "") or "").strip(),
                    "description": str(getattr(p, "description", "") or "").strip(),
                    "manufacturer": str(getattr(p, "manufacturer", "") or "").strip(),
                    "hwid": str(getattr(p, "hwid", "") or "").strip(),
                }
            )
        return details
    
    def get_port_info(self) -> dict:
        """
        获取当前串口信息
        
        Returns:
            dict: 串口信息字典
        """
        if not self.is_connected():
            return {}
        
        return {
            'port': self.port,
            'baudrate': self.baudrate,
            'bytesize': self.bytesize,
            'parity': self.parity,
            'stopbits': self.stopbits,
            'timeout': self.timeout,
            'in_waiting': self.serial_obj.in_waiting if self.serial_obj else 0
        }
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()

