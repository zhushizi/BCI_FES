"""
硬件心跳保活服务类 - 负责处理与下位机的心跳保活通信
遵循单一职责原则，专注于心跳包的接收和响应
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional
from infrastructure.hardware import SerialHardware
import logging
import time
from threading import Event, Thread

from service.business.protocol.heartbeat_frame import HeartbeatFrame


class HeartbeatStatus(Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"

    def is_alive(self) -> bool:
        return self is HeartbeatStatus.ONLINE


class HardwarePingPongService:
    """硬件心跳保活服务类 - 处理心跳包的接收和响应"""
    
    # 协议常量
    FRAME_HEADER = HeartbeatFrame.FRAME_HEADER
    FRAME_LENGTH = HeartbeatFrame.FRAME_LENGTH
    RESERVED_BYTE = HeartbeatFrame.RESERVED_BYTE
    FRAME_SIZE = HeartbeatFrame.FRAME_SIZE
    FRAME_DATA_SIZE = HeartbeatFrame.FRAME_DATA_SIZE
    RESERVED_COUNT = HeartbeatFrame.RESERVED_COUNT
    
    # 心跳模式
    HEARTBEAT_MODE = HeartbeatFrame.HEARTBEAT_MODE
    HEARTBEAT_FROM_DEVICE = HeartbeatFrame.HEARTBEAT_FROM_DEVICE
    HEARTBEAT_TO_DEVICE = HeartbeatFrame.HEARTBEAT_TO_DEVICE

    # 默认策略：每隔 N 秒主动发一次 0x02；超过 N 秒没收到 0x01 判定离线
    DEFAULT_INTERVAL_SEC = 3.0

    # 线程与时间相关常量
    MIN_INTERVAL_SEC = 0.1
    SENDER_SLEEP_SEC = 0.05
    MONITOR_SLEEP_SEC = 0.2
    JOIN_TIMEOUT_SEC = 1.0
    
    def __init__(self, serial_hardware: SerialHardware):
        """
        初始化硬件心跳保活服务
        
        Args:
            serial_hardware: 串口硬件对象
        """
        self.serial_hw = serial_hardware
        self.logger = logging.getLogger(__name__)
        self._is_enabled = False
        self._interval_sec = float(self.DEFAULT_INTERVAL_SEC)
        self._timeout_sec = float(self.DEFAULT_INTERVAL_SEC)

        # 最近一次收到下位机心跳（0x01）的时间戳；0 表示从未收到
        self._last_heartbeat_ts = 0.0
        self._status = HeartbeatStatus.UNKNOWN

        # 状态变化回调：回调参数 alive(是否在线), last_seen_sec(距上次心跳秒数，首次为 None)
        self._status_callback: Optional[Callable[[bool, Optional[float]], None]] = None
        # 状态变化回调（带枚举）
        self._state_callback: Optional[Callable[[HeartbeatStatus, Optional[float]], None]] = None

        # 后台线程控制
        self._stop_event = Event()
        self._sender_thread: Optional[Thread] = None
        self._monitor_thread: Optional[Thread] = None
        
        # 接收缓冲：下位机心跳帧可能分片到达（如 0001 + b8 或 55aa... 分多段），需先组帧再判断
        self._recv_buffer = bytearray()
        self._MAX_RECV_BUFFER = 256

        # 注册数据接收回调（允许与其他业务回调共存）
        self.serial_hw.add_data_received_callback(self._on_data_received)

    def set_status_callback(self, callback: Optional[Callable[[bool, Optional[float]], None]]) -> None:
        """设置在线/离线状态变化回调（注意：回调可能在后台线程触发）"""
        self._status_callback = callback

    def set_state_callback(self, callback: Optional[Callable[[HeartbeatStatus, Optional[float]], None]]) -> None:
        """设置在线/离线状态变化回调（枚举版，注意：回调可能在后台线程触发）"""
        self._state_callback = callback

    def configure(self, interval_sec: float = 3.0, timeout_sec: float = 3.0) -> None:
        """配置主动发送间隔和离线超时阈值（秒）"""
        self._interval_sec = float(interval_sec)
        self._timeout_sec = float(timeout_sec)
    
    def enable(self) -> None:
        """启用心跳保活功能"""
        if not self._is_enabled:
            self._is_enabled = True
            self._stop_event.clear()
            self._start_threads()
            # 启用后先按“离线”处理，直到收到下位机心跳
            self._update_status(status=HeartbeatStatus.OFFLINE, last_seen_sec=None, force=True)
            self.logger.info("心跳保活功能已启用")
    
    def disable(self) -> None:
        """禁用心跳保活功能"""
        if self._is_enabled:
            self._is_enabled = False
            self._stop_event.set()
            self._join_threads()
            self._update_status(status=HeartbeatStatus.OFFLINE, last_seen_sec=None, force=True)
            self.logger.info("心跳保活功能已禁用")
    
    def is_enabled(self) -> bool:
        """检查心跳保活功能是否启用"""
        return self._is_enabled

    def get_current_status(self) -> tuple[bool, Optional[float]]:
        """获取当前在线状态及距上次心跳秒数（首次为 None）"""
        last_seen_sec: Optional[float]
        if self._last_heartbeat_ts <= 0:
            last_seen_sec = None
        else:
            last_seen_sec = max(0.0, time.time() - self._last_heartbeat_ts)
        return self._status.is_alive(), last_seen_sec

    def get_current_state(self) -> tuple[HeartbeatStatus, Optional[float]]:
        """获取当前枚举状态及距上次心跳秒数（首次为 None）"""
        last_seen_sec: Optional[float]
        if self._last_heartbeat_ts <= 0:
            last_seen_sec = None
        else:
            last_seen_sec = max(0.0, time.time() - self._last_heartbeat_ts)
        return self._status, last_seen_sec
    
    def _on_data_received(self, data: bytes) -> None:
        """
        数据接收回调函数。下位机心跳帧可能分片到达，先写入缓冲再尝试从缓冲中解析完整 13 字节心跳包。
        """
        if not self._is_enabled or not data:
            return
        self._recv_buffer.extend(data)
        if len(self._recv_buffer) > self._MAX_RECV_BUFFER:
            self._recv_buffer = self._recv_buffer[-self._MAX_RECV_BUFFER:]
        self._try_consume_heartbeat_frames()

    def _try_consume_heartbeat_frames(self) -> None:
        """从 _recv_buffer 中尽量解析并消费完整的心跳请求帧（每帧 13 字节）。"""
        while len(self._recv_buffer) >= HeartbeatFrame.FRAME_SIZE:
            if bytes(self._recv_buffer[0:2]) != HeartbeatFrame.FRAME_HEADER:
                self._recv_buffer.pop(0)
                continue
            frame = bytes(self._recv_buffer[:HeartbeatFrame.FRAME_SIZE])
            if not HeartbeatFrame.is_heartbeat_request(frame, self.logger):
                self._recv_buffer.pop(0)
                continue
            del self._recv_buffer[:HeartbeatFrame.FRAME_SIZE]
            self._last_heartbeat_ts = self._now()
            self._update_status(status=HeartbeatStatus.ONLINE, last_seen_sec=0.0)
            self.logger.debug("收到下位机心跳包（仅刷新在线状态）")

    def _start_threads(self) -> None:
        """启动后台线程：主动发送 + 超时监控"""
        if self._sender_thread is None or not self._sender_thread.is_alive():
            self._sender_thread = Thread(target=self._sender_loop, daemon=True)
            self._sender_thread.start()
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._monitor_thread = Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def _join_threads(self) -> None:
        """停止并回收后台线程"""
        for t in (self._sender_thread, self._monitor_thread):
            if t and t.is_alive():
                t.join(timeout=self.JOIN_TIMEOUT_SEC)

    def _sender_loop(self) -> None:
        """每隔 interval_sec 主动发送一次 0x02（不依赖下位机先发 ping）"""
        next_send = 0.0
        while self._is_enabled and not self._stop_event.is_set():
            now = self._now()
            if now >= next_send:
                try:
                    self._send_heartbeat_response()
                except Exception as e:
                    self.logger.error(f"主动发送心跳响应异常: {e}")
                next_send = now + max(self.MIN_INTERVAL_SEC, float(self._interval_sec))
            time.sleep(self.SENDER_SLEEP_SEC)

    def _monitor_loop(self) -> None:
        """监控超时：超过 timeout_sec 未收到 0x01 则认为离线"""
        while self._is_enabled and not self._stop_event.is_set():
            try:
                now = self._now()
                if self._last_heartbeat_ts <= 0:
                    # 从未收到过：视为离线
                    self._update_status(status=HeartbeatStatus.OFFLINE, last_seen_sec=None)
                else:
                    delta = now - self._last_heartbeat_ts
                    status = (
                        HeartbeatStatus.ONLINE
                        if (delta <= float(self._timeout_sec))
                        else HeartbeatStatus.OFFLINE
                    )
                    self._update_status(status=status, last_seen_sec=float(delta))
            except Exception as e:
                self.logger.error(f"心跳超时监控异常: {e}")
            time.sleep(self.MONITOR_SLEEP_SEC)

    def _update_status(self, status: HeartbeatStatus, last_seen_sec: Optional[float], force: bool = False) -> None:
        """状态变化时触发回调（只在变化时触发，除非 force=True）"""
        if (not force) and (status == self._status):
            return
        self._status = status
        if self._status_callback:
            try:
                self._status_callback(self._status.is_alive(), last_seen_sec)
            except Exception as e:
                self.logger.error(f"状态回调执行失败: {e}")
        if self._state_callback:
            try:
                self._state_callback(self._status, last_seen_sec)
            except Exception as e:
                self.logger.error(f"状态回调执行失败(枚举): {e}")
    
    def _is_heartbeat_packet(self, data: bytes) -> bool:
        """
        检查是否是心跳包
        
        心跳包格式（下位机->上位机）：
        [帧头(2)] [长度(1)] [保留(1)] [模式(1)] [方向(1)] [保留(5)] [校验和(2)]
        0x55 0xAA  0x0D     0x00     0xAB     0x01      0x00...   0x?? 0x??
        
        Args:
            data: 接收到的数据
            
        Returns:
            bool: 是否是心跳包
        """
        return HeartbeatFrame.is_heartbeat_request(data, self.logger)
    
    def _send_heartbeat_response(self) -> bool:
        """
        发送心跳响应包
        
        心跳响应包格式（上位机->下位机）：
        [帧头(2)] [长度(1)] [保留(1)] [模式(1)] [方向(1)] [保留(5)] [校验和(2)]
        0x55 0xAA  0x0D     0x00     0xAB     0x02      0x00...   0x?? 0x??
        
        Returns:
            bool: 发送是否成功
        """
        if not self.serial_hw.is_connected():
            self.logger.warning("串口未连接，无法发送心跳响应")
            return False
        
        # 构建心跳响应包
        packet = self._build_heartbeat_response()
        
        # 发送数据
        success = self.serial_hw.send_data(packet)
        if success:
            self.logger.debug(f"发送心跳响应成功: {packet.hex()}")
        else:
            self.logger.error("发送心跳响应失败")
        
        return success
    
    def _build_heartbeat_response(self) -> bytes:
        """
        构建心跳响应包
        
        Returns:
            bytes: 完整的心跳响应包
        """
        return HeartbeatFrame.build_heartbeat_response()
    
    def _calculate_checksum(self, data: bytearray) -> bytes:
        """
        计算校验和（前11字节的和，返回2字节）
        
        Args:
            data: 前11字节的数据
            
        Returns:
            bytes: 2字节的校验和
        """
        return HeartbeatFrame.calculate_checksum(data)

    @staticmethod
    def _now() -> float:
        return time.time()
