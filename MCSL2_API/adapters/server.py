"""
服务器管理适配器（MCSL2_API.adapters.server）。

该层负责把“标准 API 调用”翻译成对 MCSL2 旧逻辑的调用：
- 数据源：MCSL2Lib.utils.readGlobalServerConfig()
- 运行时配置：MCSL2Lib.variables.ServerVariables
- 启动执行：MCSL2Lib.ServerControllers.processCreator.ServerLauncher

线程安全要求（强制）：
- start_server 必须是非阻塞入口：对外返回 Future，实际工作在后台线程
- 触碰 Qt 对象（ServerLauncher.start / QProcess / 信号连接）必须封送到 UI 线程
"""

from __future__ import annotations

from typing import List
from typing import Optional

from ..core import APICore
from ..models import ServerInfo
from ..models import ServerStatus
from ..models import State
from ..utils.threading import run_on_ui_thread


class ServerAdapter:
    """服务器相关 API 的 Facade（线程安全）。"""

    def __init__(self, core: Optional[APICore] = None) -> None:
        self._core = core or APICore()

    def list(self) -> List[ServerInfo]:
        """
        获取当前全局服务器列表（标准化模型）。

        Returns:
            List[ServerInfo]
        """

        try:
            from MCSL2Lib.utils import readGlobalServerConfig
        except Exception:
            self._core.interaction.notify(
                "当前环境未加载 MCSL2Lib，无法读取服务器列表。",
                level="warning",
            )
            return []

        excluded_keys = {"name", "core_file_name", "java_path", "server_type"}
        res: List[ServerInfo] = []
        for idx, d in enumerate(readGlobalServerConfig()):
            extra = {k: v for k, v in d.items() if k not in excluded_keys}
            res.append(
                ServerInfo(
                    name=str(d.get("name", "")),
                    index=idx,
                    core_file_name=d.get("core_file_name"),
                    java_path=d.get("java_path"),
                    server_type=d.get("server_type"),
                    extra=extra,
                )
            )
        return res

    def get(self, server_name: str) -> Optional[ServerInfo]:
        for s in self.list():
            if s.name == server_name:
                return s
        return None

    def status(self, server_name: str) -> ServerStatus:
        bridge = self._core.get_bridge(server_name)
        if bridge is None:
            return ServerStatus(name=server_name, state=State.STOPPED)

        try:
            running = bool(bridge.isServerRunning())
        except Exception:
            running = False

        pid = None
        exit_code = None
        try:
            proc = getattr(getattr(bridge, "serverProcess", None), "process", None)
            if proc is not None:
                try:
                    pid = int(proc.processId())
                except Exception:
                    pid = None
                try:
                    exit_code = int(proc.exitCode())
                except Exception:
                    exit_code = None
        except Exception:
            pass

        return ServerStatus(
            name=server_name,
            state=State.RUNNING if running else State.STOPPED,
            pid=pid,
            exit_code=exit_code,
            players=None,
        )

    def status_async(self, server_name: str):
        return self._core.threading.submit(self.status, server_name)

    def start_server(self, server_name: str) -> bool:
        """
        启动服务器（同步版本，供内部/后台线程调用）。

        规则：
        1) 在全局列表查 name -> index
        2) 在 UI 线程创建 ServerVariables/ServerLauncher 并调用 start()
        3) 取得 bridge 后立刻注册到 EventBus 做 Hook

        Returns:
            bool: 是否成功触发启动（EULA 未同意/找不到服务器会返回 False）
        """

        try:
            from MCSL2Lib.utils import readGlobalServerConfig
        except Exception:
            self._core.interaction.notify(
                "当前环境未加载 MCSL2Lib，无法启动服务器。",
                level="error",
            )
            return False

        cfg_list = readGlobalServerConfig()
        index = None
        for i, d in enumerate(cfg_list):
            if d.get("name") == server_name:
                index = i
                break
        if index is None:
            self._core.interaction.notify(f"未找到服务器：{server_name}", level="error")
            return False

        try:
            self._core.events.install_hooks()
        except Exception:
            self._core.interaction.notify(
                "安装启动 Hook 失败，无法捕获服务器事件。",
                level="warning",
            )

        def _start_on_ui() -> object:
            from MCSL2Lib.ServerControllers.processCreator import ServerConfigConstructor
            from MCSL2Lib.ServerControllers.processCreator import ServerLauncher

            v = ServerConfigConstructor.loadServerConfig(index=index)
            launcher = ServerLauncher(v)
            return launcher.start()

        try:
            result = run_on_ui_thread(_start_on_ui, wait=True)
        except Exception:
            self._core.interaction.notify(f"启动服务器失败：{server_name}", level="error")
            return False

        try:
            from MCSL2Lib.ServerControllers.processCreator import _MinecraftEULA  # type: ignore
        except Exception:
            self._core.interaction.notify(
                "当前环境未加载 MCSL2Lib，无法解析启动结果。",
                level="error",
            )
            return False

        if isinstance(result, _MinecraftEULA):
            self._core.interaction.notify(
                f"服务器「{server_name}」未同意 EULA，无法启动。", level="warning"
            )
            return False

        bridge = result
        self._core.events.hook_bridge(bridge, server_name=server_name)
        return True

    def start(self, server_name: str):
        """
        启动服务器（异步版本，对外推荐）。

        Returns:
            concurrent.futures.Future[bool]
        """

        return self._core.threading.submit(self.start_server, server_name)

    def accept_eula(self, server_name: str) -> bool:
        try:
            from MCSL2Lib.ServerControllers.processCreator import _MinecraftEULA  # type: ignore

            _MinecraftEULA(server_name).acceptEula()
            return True
        except Exception:
            self._core.interaction.notify(f"写入 EULA 失败：{server_name}", level="error")
            return False

    def stop_server(self, server_name: str, *, force: bool = False) -> bool:
        bridge = self._core.get_bridge(server_name)
        if bridge is None:
            self._core.interaction.notify(
                f"未找到运行中的服务器桥接：{server_name}",
                level="warning",
            )
            return False

        def _stop_on_ui() -> None:
            if force:
                bridge.haltServer()
            else:
                bridge.stopServer()

        try:
            run_on_ui_thread(_stop_on_ui, wait=False)
            return True
        except Exception:
            self._core.interaction.notify(f"停止服务器失败：{server_name}", level="error")
            return False

    def stop(self, server_name: str, *, force: bool = False):
        return self._core.threading.submit(self.stop_server, server_name, force=force)

    def restart_server(self, server_name: str) -> bool:
        bridge = self._core.get_bridge(server_name)
        if bridge is None:
            self._core.interaction.notify(
                f"未找到运行中的服务器桥接：{server_name}",
                level="warning",
            )
            return False

        try:
            run_on_ui_thread(lambda: bridge.restartServer(), wait=False)
            return True
        except Exception:
            self._core.interaction.notify(f"重启服务器失败：{server_name}", level="error")
            return False

    def restart(self, server_name: str):
        return self._core.threading.submit(self.restart_server, server_name)

    def command_server(self, server_name: str, command: str) -> bool:
        bridge = self._core.get_bridge(server_name)
        if bridge is None:
            self._core.interaction.notify(
                f"未找到运行中的服务器桥接：{server_name}",
                level="warning",
            )
            return False

        try:
            run_on_ui_thread(lambda: bridge.sendCommand(str(command)), wait=False)
            return True
        except Exception:
            self._core.interaction.notify(f"发送命令失败：{server_name}", level="error")
            return False

    def command(self, server_name: str, command: str):
        return self._core.threading.submit(self.command_server, server_name, command)
