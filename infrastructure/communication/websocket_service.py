from __future__ import annotations

"""
主控程序（MainController）的 WebSocket(JSON-RPC 2.0) 客户端。

协议参考：华伟脑机接口设备 JSON-RPC 的通信协议.pdf
- 默认 WebSocket 地址：ws://127.0.0.1:8080
- 连接后必须先 register：{"jsonrpc":"2.0","method":"register","params":{"type":"main"}}
- 三方角色：main / paradigm / decoder
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import websockets


JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class JsonRpcError(Exception):
    code: int
    message: str
    data: Any = None

    def to_dict(self) -> JsonDict:
        err: JsonDict = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ws_is_open(ws: Any) -> bool:
    """
    兼容 websockets 不同版本的连接对象状态判断。

    - 旧版(legacy) WebSocketClientProtocol: ws.closed / ws.open
    - 新版(asyncio) ClientConnection: 没有 ws.closed，通常有 ws.state / ws.close_code
    """
    if ws is None:
        return False

    closed = getattr(ws, "closed", None)
    if isinstance(closed, bool):
        return not closed

    opened = getattr(ws, "open", None)
    if isinstance(opened, bool):
        return opened

    # websockets>=12 可能提供 state 枚举
    state = getattr(ws, "state", None)
    if state is not None:
        try:
            from websockets.protocol import State  # type: ignore

            return state == State.OPEN
        except Exception:
            # 无法导入 State 时退化：靠 close_code 判断
            pass

    close_code = getattr(ws, "close_code", None)
    return close_code is None


def build_notification(method: str, params: Optional[JsonDict] = None) -> JsonDict:
    msg: JsonDict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def build_request(method: str, params: Optional[JsonDict], req_id: int) -> JsonDict:
    msg: JsonDict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    return msg


def build_result(result: Any, req_id: Any) -> JsonDict:
    # 协议文档示例中 id 可能为 null，这里保持兼容
    return {"jsonrpc": "2.0", "result": result, "id": req_id}


def build_error(err: JsonRpcError, req_id: Any) -> JsonDict:
    return {"jsonrpc": "2.0", "error": err.to_dict(), "id": req_id}


class MainWebSocketService:
    """
    MainController 侧 WebSocket 服务（客户端）。

    - 在后台线程启动 asyncio loop，避免阻塞 Qt 主线程
    - 提供 JSON-RPC 的 request/notification 发送
    - 支持按 method 注册回调，统一处理三方消息
    """

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8080",
        client_type: str = "main",
        enable_heartbeat: bool = True,
        heartbeat_interval_sec: float = 5.0,
        max_message_size: Optional[int] = None,
    ) -> None:
        self.url = url
        self.client_type = client_type
        self.enable_heartbeat = bool(enable_heartbeat)
        self.heartbeat_interval_sec = float(heartbeat_interval_sec)
        self.max_message_size = max_message_size

        self.logger = logging.getLogger(__name__)

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # websockets 新版返回 ClientConnection，旧版为 WebSocketClientProtocol；这里用 Any 避免绑死类型
        self._ws: Optional[Any] = None

        self._next_id = 1000
        self._pending: Dict[int, asyncio.Future] = {}
        self._handlers: Dict[str, Callable[[JsonDict], None]] = {}
        self._prefix_handlers: list[tuple[str, Callable[[JsonDict], None]]] = []
        self._binary_handlers: list[Callable[[bytes], None]] = []

        # 一些主控侧状态，可按需扩展
        self.decoder_ready: bool = False
        self.decoder_info: JsonDict = {}

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_thread, name="MainWebSocketService", daemon=True)
        self._thread.start()

    def stop(self, timeout_sec: float = 2.0) -> None:
        self._stop_flag.set()
        try:
            if self._loop:
                asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_sec)

    def is_connected(self) -> bool:
        return _ws_is_open(self._ws)

    # ---------- 回调注册 ----------
    def on(self, method: str, handler: Callable[[JsonDict], None]) -> None:
        """注册 JSON-RPC method 的通知处理器（在 WS 后台线程中回调）。"""
        self._handlers[str(method)] = handler

    def on_prefix(self, method_prefix: str, handler: Callable[[JsonDict], None]) -> None:
        """
        注册 method 前缀处理器（例如 'decoder.' / 'paradigm.'）。
        当没有命中精确 method handler 时，会按前缀顺序匹配并回调。
        """
        self._prefix_handlers.append((str(method_prefix), handler))

    def on_binary(self, handler: Callable[[bytes], None]) -> None:
        """注册二进制消息处理器（在 WS 后台线程中回调）。"""
        self._binary_handlers.append(handler)

    def send_jsonrpc(self, payload: JsonDict) -> None:
        """
        发送一条“原始 JSON-RPC”消息（notification / request / response 均可）。
        用于上层网关直接转发协议包。
        """
        if not self._loop:
            self.logger.warning("WebSocket loop 未启动，丢弃发送")
            return
        asyncio.run_coroutine_threadsafe(self._send_json(payload), self._loop)

    # ---------- 发送（线程安全） ----------
    def send_notification(self, method: str, params: Optional[JsonDict] = None) -> None:
        if not self._loop:
            self.logger.warning("WebSocket loop 未启动，丢弃发送")
            return
        msg = build_notification(method, params=params) # 构建消息
        asyncio.run_coroutine_threadsafe(self._send_json(msg), self._loop) # 发送消息到WebSocket

    def send_request(self, method: str, params: Optional[JsonDict] = None, timeout_sec: float = 10.0) -> Any:
        """
        发送 request 并等待 result/error（在调用线程阻塞等待）。
        若你在 Qt 主线程调用且不想阻塞，请改为自己用线程或回调封装。
        """
        if not self._loop:
            raise RuntimeError("WebSocket loop 未启动")

        req_id = self._alloc_id()
        msg = build_request(method, params=params, req_id=req_id)

        fut = asyncio.run_coroutine_threadsafe(self._request_and_wait(req_id, msg, timeout_sec), self._loop)
        return fut.result(timeout=timeout_sec + 1.0)

    # ---------- 主控常用 API（按协议命名） ----------
    def send_exo_action_complete(self, trial_index: int, executed_action: str) -> None:
        self.send_notification(
            "main.exo_action_complete",
            {"trial_index": int(trial_index), "executed_action": str(executed_action)},
        )

    def stop_session(self, reason: str = "user_requested", request_id: int = 1001, timeout_sec: float = 10.0) -> Any:
        # 协议示例：main.stop_session 是 request，需要 id，并等待 decoder 的 result（报告）
        if not self._loop:
            raise RuntimeError("WebSocket loop 未启动")
        msg = build_request("main.stop_session", {"reason": str(reason)}, req_id=int(request_id))
        fut = asyncio.run_coroutine_threadsafe(self._request_and_wait(int(request_id), msg, timeout_sec), self._loop)
        return fut.result(timeout=timeout_sec + 1.0)

    def emergency_stop(
        self, reason: str, details: Optional[JsonDict] = None, action_required: str = "halt_immediately"
    ) -> None:
        params: JsonDict = {"reason": str(reason), "action_required": str(action_required)}
        if details:
            params["details"] = details
        self.send_notification("main.emergency_stop", params)

    # ---------- 内部实现 ----------
    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _run_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run_forever())

    async def _run_forever(self) -> None:
        backoff = 1.0
        while not self._stop_flag.is_set():
            try:
                await self._connect_and_loop()
                backoff = 1.0
            except Exception as e:
                self.logger.error(f"WebSocket 运行异常，将重连: {e}")
                await asyncio.sleep(min(backoff, 10.0))
                backoff *= 2.0

    async def _connect_and_loop(self) -> None:
        self.logger.info(f"连接 WebSocket: {self.url}")
        async with websockets.connect(
            self.url,
            ping_interval=None,
            max_size=self.max_message_size,
        ) as ws:
            self._ws = ws
            await self._register()
            self.logger.info(f"WebSocket 已连接并注册为: {self.client_type}")

            recv_task = asyncio.create_task(self._recv_loop())
            tasks = [recv_task]
            if self.enable_heartbeat:
                tasks.append(asyncio.create_task(self._heartbeat_loop()))

            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

    async def _register(self) -> None:
        msg = build_notification("register", {"type": self.client_type})
        await self._send_json(msg)

    async def _close_ws(self) -> None:
        ws = self._ws
        self._ws = None
        if ws and _ws_is_open(ws):
            try:
                await ws.close()
            except Exception:
                pass

    async def _send_json(self, payload: JsonDict) -> None:
        ws = self._ws
        if not _ws_is_open(ws):
            self.logger.warning(f"WebSocket 未连接，无法发送: {payload}")
            return
        raw = json.dumps(payload, ensure_ascii=False)
        await ws.send(raw)

    async def _request_and_wait(self, req_id: int, msg: JsonDict, timeout_sec: float) -> Any:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[int(req_id)] = fut
        await self._send_json(msg)
        try:
            return await asyncio.wait_for(fut, timeout=timeout_sec)
        finally:
            self._pending.pop(int(req_id), None)

    async def _heartbeat_loop(self) -> None:
        while _ws_is_open(self._ws) and not self._stop_flag.is_set():
            try:
                # 协议文档示例：system.ping 作为通知发送，带电池/连接状态
                self.send_notification(
                    "system.ping",
                    {
                        "battery_level": 0,
                        "connection_status": "ok",
                        "timestamp_ms": _now_ms(),
                    },
                )
            except Exception as e:
                self.logger.debug(f"心跳发送失败: {e}")
            await asyncio.sleep(self.heartbeat_interval_sec)

    async def _recv_loop(self) -> None:
        ws = self._ws
        assert ws is not None
        try:
            async for raw in ws:
                if isinstance(raw, (bytes, bytearray)):
                    self._handle_binary(bytes(raw))
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    self.logger.warning(f"收到非 JSON 消息: {raw!r}")
                    continue
                self._handle_incoming(msg)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.warning(f"WebSocket 连接关闭: {e}")

    def _handle_binary(self, payload: bytes) -> None:
        if not self._binary_handlers:
            self.logger.info("收到二进制消息但无处理器")
            return
        for handler in list(self._binary_handlers):
            try:
                handler(payload)
            except Exception as e:
                self.logger.error(f"处理二进制消息异常: {e}")

    def _handle_incoming(self, msg: JsonDict) -> None:
        # JSON-RPC response
        if "id" in msg and ("result" in msg or "error" in msg):
            req_id = msg.get("id")
            if isinstance(req_id, int) and req_id in self._pending:
                fut = self._pending[req_id]
                if "error" in msg:
                    fut.set_exception(RuntimeError(msg["error"]))
                else:
                    fut.set_result(msg.get("result"))
            else:
                # 兼容：id 为 null 或者没有 pending 的情况，直接日志
                self.logger.info(f"收到 response（无等待者）: {msg}")
            return

        method = msg.get("method")
        params = msg.get("params") or {}

        handler = self._handlers.get(str(method)) if method else None
        if handler:
            try:
                handler(msg)
            except Exception as e:
                self.logger.error(f"处理 method={method} 异常: {e}")

        # 尝试前缀匹配（广播语义：允许多个订阅者同时收到同一条消息）
        prefix_matched = False
        if method:
            m = str(method)
            for prefix, ph in list(self._prefix_handlers):
                if m.startswith(prefix):
                    prefix_matched = True
                    try:
                        ph(msg)
                    except Exception as e:
                        self.logger.error(f"处理 method 前缀={prefix} 异常: {e}")

        # 无任何 handler 命中时，保持日志可见性
        if not handler and not prefix_matched:
            self.logger.info(f"收到通知: {msg}")

