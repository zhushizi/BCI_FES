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


class SerialHardware:
    """串口硬件通信类"""
    
    def __init__(self, port: str = None, baudrate: int = 115200,
                 timeout: float = 1.0, bytesize: int = 8,
                 parity: str = 'N', stopbits: int = 1,
                 log_receive_enabled: bool = True):
        """
        初始化串口通信
        
        Args:
            port: 串口名称，如 'COM3' 或 '/dev/ttyUSB0'，None 则自动检测
            baudrate: 波特率，默认 115200
            timeout: 超时时间（秒），默认 1.0
            bytesize: 数据位，默认 8
            parity: 校验位，'N'(无校验), 'E'(偶校验), 'O'(奇校验)
            stopbits: 停止位，1 或 2
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        
        self.serial_obj: Optional[serial.Serial] = None
        self.is_connected_flag = False
        self.data_received_callback: Optional[Callable[[bytes], None]] = None
        self._data_received_callbacks: list[Callable[[bytes], None]] = []
        self.receive_thread: Optional[Thread] = None
        self.receive_running = False
        self.log_receive_enabled = bool(log_receive_enabled)
        
        self.logger = logging.getLogger(__name__)
    
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
            if self.log_receive_enabled:
                self.logger.info(f"[发送指令] 数据: {data.hex()} ({len(data)} 字节)")
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
                if self.log_receive_enabled:
                    # 使用 INFO 级别，确保在终端打印
                    self.logger.info(f"[接收指令] 数据: {data.hex()} ({len(data)} 字节)")
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
                        if self.log_receive_enabled:
                            # 使用 INFO 级别，确保在终端打印接收到的数据
                            self.logger.info(f"[接收指令] 数据: {data.hex()} ({len(data)} 字节)")
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

