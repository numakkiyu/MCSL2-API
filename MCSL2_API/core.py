"""
MCSL2_API 核心对象（APICore）。

APICore 是一个轻量级的单例“运行时容器”，主要职责：
- 注入并持有 MCSL2 的核心对象 Window（上帝对象）
- 统一提供：线程池、事件总线、交互提供者
- 作为 Facade 的内部依赖（API/server/events 都从这里拿能力）

线程约束：
- 任何 UI 操作必须使用 utils.threading.run_on_ui_thread 封送回主线程。
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any
from typing import Optional

from .events.bus import EventBus
from .interaction import HeadlessInteraction
from .interaction import InteractionProvider
from .interaction import QtInteraction
from .utils.threading import ThreadManager
from .utils.threading import ensure_ui_ready


@dataclass(frozen=True)
class BackendRef:
    backend_window: Any


class UnsafeAccess:
    def __init__(self, core: "APICore") -> None:
        self._core = core

    @property
    def backend_window(self) -> Any:
        return self._core.backend_window

    def require_backend(self) -> Any:
        w = self._core.backend_window
        if w is None:
            raise RuntimeError("MCSL2_API 尚未注入 backend（Window）。")
        return w

    def import_module(self, module: str) -> Any:
        import importlib

        return importlib.import_module(module)

    def mcsl2lib(self) -> Any:
        return self.import_module("MCSL2Lib")

    def bridge(self, server_name: str) -> Any:
        return self._core.get_bridge(server_name)


class APICore:
    """MCSL2_API 单例核心容器。"""

    _instance: Optional["APICore"] = None

    def __new__(cls) -> "APICore":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._backend_ref = None
            inst._bridges = {}
            inst._bridges_lock = threading.RLock()
            inst.threading = ThreadManager()
            inst.events = EventBus()
            inst.interaction = HeadlessInteraction()
            inst.unsafe_access = UnsafeAccess(inst)
            cls._instance = inst
        return cls._instance

    @property
    def backend_window(self) -> Any:
        """返回注入的 MCSL2 主窗口 Window 单例实例。"""

        ref = self._backend_ref
        return None if ref is None else ref.backend_window

    def inject_backend(self, backend_window: Any) -> None:
        """
        注入 MCSL2 主窗口实例（Window 单例）。

        插件侧推荐用法：
            from MCSL2Lib.windowInterface import Window
            from MCSL2_API import core
            core.inject_backend(Window())

        注入后：
        - interaction 自动切换为 QtInteraction（GUI 环境）
        - events.install_hooks 可安全进行（需要 Qt event loop）
        """

        try:
            self._backend_ref = BackendRef(backend_window=backend_window)
            ensure_ui_ready()
            try:
                from PyQt5.QtWidgets import QWidget  # type: ignore

                if isinstance(backend_window, QWidget):
                    self.interaction = QtInteraction(parent=backend_window)
                else:
                    self.interaction = HeadlessInteraction()
            except Exception:
                self.interaction = HeadlessInteraction()
        except Exception:
            self._backend_ref = None
            self.interaction = HeadlessInteraction()

    def set_interaction(self, provider: InteractionProvider) -> None:
        """显式替换交互提供者（用于自定义 UI/JSON 输出等）。"""

        self.interaction = provider

    def register_bridge(self, server_name: str, bridge: Any) -> None:
        with self._bridges_lock:
            self._bridges[str(server_name)] = bridge

    def get_bridge(self, server_name: str) -> Any:
        with self._bridges_lock:
            return self._bridges.get(str(server_name))
