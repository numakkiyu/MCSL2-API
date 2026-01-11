"""
事件总线 + Hook（MCSL2_API.events.bus）。

功能：
1) 提供装饰器式订阅接口：@Event.on(Event.Log) / @Event.on(Event.ServerExit)
2) 默认将事件回调派发到后台线程，避免阻塞 GUI 主线程
3) install_hooks(): monkeypatch MCSL2Lib.ServerControllers.processCreator.ServerLauncher.start
   - 无论是 UI 点击启动，还是 API 调用启动，都能截获返回的 _ServerProcessBridge
   - 将 bridge.serverLogOutput/serverClosed 信号转化为标准化事件并分发

重要约束：
- 不能臆造 MCSL2 内部类名：必须以 processCreator.py 的 ServerLauncher/_ServerProcessBridge 为准
- Hook 必须“非侵入式”：只 monkeypatch，不改 MCSL2Lib 源码
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import DefaultDict
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import TypeVar

from ..models import LogEvent
from ..models import ServerExitEvent


TEvent = TypeVar("TEvent", bound=object)
Handler = Callable[[Any], Any]


@dataclass(frozen=True)
class _HandlerRef:
    fn: Handler
    background: bool
    priority: int


class EventBus:
    """线程安全事件总线（默认后台派发）。"""

    def __init__(self) -> None:
        from collections import defaultdict

        self._handlers: DefaultDict[Type[Any], List[_HandlerRef]] = defaultdict(list)
        self._hooks_installed = False
        self._bridge_hooks: Dict[Tuple[str, int], bool] = {}
        self._lock = threading.RLock()

    def on(
        self,
        event_type: Type[TEvent],
        *,
        background: bool = True,
        priority: int = 0,
    ) -> Callable[[Handler], Handler]:
        """
        订阅一个事件类型。

        Args:
            event_type: 事件类（例如 LogEvent）。
            background: True 表示回调在线程池中执行，避免阻塞 UI。
        """

        def decorator(fn: Handler) -> Handler:
            with self._lock:
                self._handlers[event_type].append(
                    _HandlerRef(fn=fn, background=background, priority=int(priority))
                )
            return fn

        return decorator

    def subscribe(
        self,
        fn: Optional[Handler] = None,
        *,
        event_type: Optional[Type[Any]] = None,
        background: bool = True,
        priority: int = 0,
    ):
        def decorator(real_fn: Handler) -> Handler:
            et = event_type
            if et is None:
                et = _infer_event_type(real_fn)
            if et is None:
                raise TypeError(
                    "无法推断事件类型：请为事件参数添加类型注解，或显式传入 event_type。"
                )
            return self.on(et, background=background, priority=priority)(real_fn)

        if fn is None:
            return decorator
        return decorator(fn)

    def emit(self, event: Any) -> None:
        """
        发送事件。

        默认会把订阅回调丢到 ThreadPoolExecutor，避免阻塞主线程。
        """

        from ..core import APICore

        core = APICore()
        with self._lock:
            refs = list(self._handlers.get(type(event), []))
        refs.sort(key=lambda r: r.priority, reverse=True)
        for ref in refs:
            if getattr(event, "cancelled", False):
                return
            if ref.background:
                core.threading.submit(self._safe_call, ref.fn, event)
            else:
                self._safe_call(ref.fn, event)

    def _safe_call(self, fn: Handler, event: Any) -> None:
        try:
            fn(event)
        except Exception:
            try:
                from MCSL2Lib.utils import MCSL2Logger  # type: ignore

                MCSL2Logger.error(msg=f"MCSL2_API 事件回调异常: {type(event).__name__}")
            except Exception:
                pass

    def hook_bridge(self, bridge: Any, server_name: str) -> None:
        """
        将 _ServerProcessBridge 的 PyQt 信号转化为标准事件。

        Args:
            bridge: MCSL2Lib.ServerControllers.processCreator._ServerProcessBridge 实例
            server_name: 服务器名称
        """

        key = (server_name, id(bridge))
        with self._lock:
            if self._bridge_hooks.get(key):
                return
            self._bridge_hooks[key] = True

        def _on_log(line: str) -> None:
            self.emit(LogEvent(server_name=server_name, content=str(line), ts=time.time()))

        def _on_closed(exit_code: int) -> None:
            self.emit(
                ServerExitEvent(
                    server_name=server_name,
                    exit_code=int(exit_code),
                    ts=time.time(),
                )
            )

        try:
            bridge.serverLogOutput.connect(_on_log)
        except Exception:
            pass
        try:
            bridge.serverClosed.connect(_on_closed)
        except Exception:
            pass
        try:
            from ..core import APICore

            APICore().register_bridge(server_name=server_name, bridge=bridge)
        except Exception:
            pass

    def install_hooks(self) -> None:
        """
        安装 Hook（monkeypatch ServerLauncher.start）。

        Hook 目标：MCSL2Lib.ServerControllers.processCreator.ServerLauncher.start
        - 原函数会返回 _ServerProcessBridge 或 _MinecraftEULA
        - 我们在返回 bridge 时立刻 hook 信号并 emit 标准事件
        """

        with self._lock:
            if self._hooks_installed:
                return

        try:
            from MCSL2Lib.ServerControllers import processCreator as pc  # type: ignore
        except Exception:
            return

        ServerLauncher = getattr(pc, "ServerLauncher", None)
        if ServerLauncher is None:
            return

        original_start = getattr(ServerLauncher, "start", None)
        if original_start is None:
            return

        if hasattr(original_start, "__mcsl2_api_hooked__"):
            with self._lock:
                self._hooks_installed = True
            return

        bus = self

        def start_wrapper(self_obj):  # type: ignore[no-untyped-def]
            result = original_start(self_obj)
            try:
                server_name = (
                    getattr(getattr(self_obj, "config", None), "serverName", "") or ""
                )
                if server_name and result is not None:
                    from MCSL2Lib.ServerControllers.processCreator import (  # type: ignore
                        _MinecraftEULA,
                    )

                    if not isinstance(result, _MinecraftEULA):
                        bus.hook_bridge(result, server_name=server_name)
            except Exception:
                pass
            return result

        setattr(start_wrapper, "__mcsl2_api_hooked__", True)
        setattr(ServerLauncher, "start", start_wrapper)
        with self._lock:
            self._hooks_installed = True


class Cancellable:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _infer_event_type(fn: Handler) -> Optional[Type[Any]]:
    try:
        import inspect

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if not params:
            return None
        if params[0].name == "self" and len(params) >= 2:
            p = params[1]
        else:
            p = params[0]
        ann = p.annotation
        if ann is inspect._empty:
            return None
        if isinstance(ann, str):
            return None
        return ann
    except Exception:
        return None
