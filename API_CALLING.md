# MCSL2_API 使用与开发手册

面向 **MCSL2 插件开发者** 的使用文档与 API 参考，覆盖：
* 如何通过 `MCSL2_API` 与 MCSL2 主程序通信（服务器/界面/下载/事件）
* 如何规范地写插件（加载器约定、生命周期、线程模型）
* 如何分发插件（终端用户零操作的 Vendor 模式）

*   **PyPI 包名**：`mcsl2-api`
*   **Python 导入名**：`MCSL2_API`
*   **License**：MIT（见 [LICENSE](LICENSE)）

---

## 目录

1. [30 秒上手](#1-30-秒上手)
2. [安装与分发](#2-安装与分发)
3. [MCSL2 插件加载器约定](#3-mcsl2-插件加载器约定)
4. [通信与线程模型](#4-通信与线程模型)
5. [插件写法（模板）](#5-插件写法模板)
6. [实战：可复制的完整例子](#6-实战可复制的完整例子)
7. [API 参考（与当前代码一致）](#7-api-参考与当前代码一致)
8. [故障排查](#8-故障排查)

---

## 1. 30 秒上手

一个“能跑起来”的插件至少要做三件事：
1. 让 MCSL2 能 import 到你的插件模块（命名约定）
2. 注入 `Window()`（让 API 拿到宿主上下文）
3. 安装 Hook（把日志/退出转成事件）

下面示例同时兼容“开发者有 pip 环境”和“用户无 pip 环境”（Vendor 模式）。把它放到 `Plugins/HelloPlugin/HelloPlugin.py` 里即可。

```python
from __future__ import annotations

import os
import sys

_vendor_dir = os.path.join(os.path.dirname(__file__), "_vendor")
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

from MCSL2Lib.windowInterface import Window  # type: ignore
from MCSL2_API import API, Event, Plugin, PluginContext, PluginManifest


manifest = PluginManifest(
    id="com.example.hello",
    version="1.0.0",
    dependencies=[],
    permissions=[],
    name="HelloPlugin",
    description="演示：注入、Hook、事件、UI 注入、服务器命令",
    authors=[],
)


class HelloPluginImpl(Plugin):
    def on_load(self, context: PluginContext) -> None:
        return

    def on_enable(self, context: PluginContext) -> None:
        context.core.inject_backend(Window())
        context.core.events.install_hooks()

        API.ui.add_button(
            "pluginsInterface.pluginsVerticalLayout",
            "发送 say Hello",
            on_click=lambda: API.server.command("生存服", "say Hello from MCSL2_API"),
            primary=True,
        )

        @Event.on(Event.Log)
        def _on_log(e: Event.Log) -> None:
            if e.server_name == "生存服" and "Done" in (e.content or ""):
                API.interaction.notify("生存服启动完成", title="HelloPlugin", level="success")

        context.interaction.notify("HelloPlugin 已启用", title="HelloPlugin", level="info")

    def on_disable(self, context: PluginContext) -> None:
        return


HelloPlugin = HelloPluginImpl.export(manifest=manifest, plugin_name="HelloPlugin")
```

---

## 2. 安装与分发

### 2.1 开发者安装（有 Python 环境）

```bash
pip install mcsl2-api

# 可选依赖
pip install "mcsl2-api[pydantic]"
pip install "mcsl2-api[http]"
pip install "mcsl2-api[all]"
```

### 2.2 用户分发（Vendor 模式）

终端用户通常只运行编译后的 `exe`，没有 pip 环境。开发者建议：
1. 把 `MCSL2_API/` 整个目录复制到插件 `_vendor/` 下
2. 在插件入口文件顶部注入 `_vendor` 到 `sys.path`（必须在 `import MCSL2_API` 之前）

推荐目录结构：

```text
Plugins/
└── MyPlugin/
    ├── config.json
    ├── MyPlugin.py
    └── _vendor/
        └── MCSL2_API/
            ├── __init__.py
            └── ...
```

入口注入模板：

```python
import os
import sys

_vendor_dir = os.path.join(os.path.dirname(__file__), "_vendor")
if _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
```

---

## 3. MCSL2 插件加载器约定

MCSL2 的插件加载器是“约定优先”，核心要点：

### 3.1 目录与入口名必须一致

等价导入行为可以理解为：

```python
__import__(f"Plugins.{pluginName}.{pluginName}", fromlist=[pluginName])
```

所以你必须满足：

```text
Plugins/
└── DemoPlugin/
    ├── config.json
    └── DemoPlugin.py
```

并且在 `DemoPlugin.py` 里导出一个与 `pluginName` 同名的全局变量。传统写法是：

```python
from Adapters.Plugin import Plugin

DemoPlugin = Plugin()
```

现代写法使用 `Plugin.export(...)` 会自动把这个同名变量导出（见后文模板）。

### 3.2 生命周期执行时机

MCSL2 侧生命周期由 `Adapters.Plugin.Plugin` 承载，支持三段回调：
* LOAD：首次导入时调用（若注册）
* ENABLE：用户在插件页打开开关时调用（若注册）
* DISABLE：用户关闭开关时调用（若注册）

重要细节：
* Python 模块会驻留在 `sys.modules`，禁用再启用不一定会重新 import
* 不要把“必须执行的初始化”放在模块顶层；放在 ENABLE/LOAD

---

## 4. 通信与线程模型

### 4.1 Window 注入（必须理解）

绝大多数与宿主交互的能力都需要 MCSL2 主窗口 `Window()`：

```python
from MCSL2Lib.windowInterface import Window  # type: ignore
from MCSL2_API import core

core.inject_backend(Window())
```

注入后：
* `core.backend_window` 可用
* `API.interaction` 会尽量切换到 GUI 交互提供者（弹窗/通知）

### 4.2 Hook 与事件桥接

安装 Hook 后，MCSL2 的 `ServerLauncher.start()` 返回的 bridge 信号会被转换成标准事件：

```python
from MCSL2_API import core

core.events.install_hooks()
```

事件来源：
* `bridge.serverLogOutput` -> `Event.Log`
* `bridge.serverClosed` -> `Event.ServerExit`

### 4.3 线程模型（强制约束）

原则：
* 不要阻塞 UI 线程
* 触碰 Qt 对象必须回 UI 线程

MCSL2_API 的默认行为：
* `API.server.start/stop/restart/command`：对外返回 `Future`，内部自动封送 UI 线程处理 Qt 对象
* `API.ui.*`：内部自动封送到 UI 线程执行
* `Event.on(...)`：默认 `background=True`，回调会丢到线程池执行（避免阻塞 GUI）

如果你需要手动控制线程：
* `core.threading.submit(fn, *args)`：提交到线程池，返回 `Future`
* `MCSL2_API.utils.threading.run_on_ui_thread(fn, wait=...)`：封送到 UI 线程

---

## 5. 插件写法（模板）

### 5.1 现代插件（推荐）

现代写法的目标：让插件逻辑集中在一个类里，并自动完成：
* 生命周期绑定到宿主 `Adapters.Plugin.Plugin()`
* 异常隔离（宿主不中断）
* 装饰器订阅事件（可选）

```python
from __future__ import annotations

from MCSL2_API import Plugin, PluginContext, PluginManifest

manifest = PluginManifest(
    id="com.example.myplugin",
    version="1.0.0",
    dependencies=[],
    permissions=[],
    name="示例插件",
    description="现代插件模板",
    authors=[],
)


class MyPluginImpl(Plugin):
    def on_load(self, context: PluginContext) -> None:
        return

    def on_enable(self, context: PluginContext) -> None:
        return

    def on_disable(self, context: PluginContext) -> None:
        return


MyPlugin = MyPluginImpl.export(manifest=manifest, plugin_name="MyPlugin")
```

### 5.2 原生插件（兼容模式）

适合只想写少量脚本、或需要完全按宿主原生流程组织代码的情况：

```python
from Adapters.Plugin import Plugin
from MCSL2Lib.windowInterface import Window  # type: ignore
from MCSL2_API import API, core

MyPlugin = Plugin()


def enable() -> None:
    core.inject_backend(Window())
    core.events.install_hooks()
    API.interaction.notify("插件已启用", title="MyPlugin", level="info")


def disable() -> None:
    return


MyPlugin.register_enableFunc(enable)
MyPlugin.register_disableFunc(disable)
```

---

## 6. 实战：可复制的完整例子

目标：演示“与宿主通信”的关键链路
* 列出服务器 -> 启动 -> 监听日志 -> 注入 UI 按钮 -> 发送命令

```python
from __future__ import annotations

import os
import sys

_vendor_dir = os.path.join(os.path.dirname(__file__), "_vendor")
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

from MCSL2Lib.windowInterface import Window  # type: ignore
from MCSL2_API import API, Event, Plugin, PluginContext, PluginManifest


manifest = PluginManifest(
    id="demo.api.full",
    version="1.0.0",
    dependencies=[],
    permissions=[],
    name="DemoFull",
    description="演示：server/ui/event",
    authors=[],
)


class DemoFullImpl(Plugin):
    def on_load(self, context: PluginContext) -> None:
        return

    def on_enable(self, context: PluginContext) -> None:
        context.core.inject_backend(Window())
        context.core.events.install_hooks()

        servers = API.server.list()
        if not servers:
            context.interaction.notify("未读取到服务器列表", title="DemoFull", level="warning")
            return

        target = servers[0].name
        API.server.start(target)

        API.ui.add_button(
            "pluginsInterface.pluginsVerticalLayout",
            f"对 {target} 发送 say",
            on_click=lambda: API.server.command(target, "say Hello from DemoFull"),
            primary=True,
        )

        @Event.on(Event.Log)
        def _on_log(e: Event.Log) -> None:
            if e.server_name != target:
                return
            if "Done" in (e.content or ""):
                API.interaction.notify(f"{target} 启动完成", title="DemoFull", level="success")

    def on_disable(self, context: PluginContext) -> None:
        return


DemoFull = DemoFullImpl.export(manifest=manifest, plugin_name="DemoFull")
```

---

## 7. API 参考（与当前代码一致）

本节以仓库当前实现为准（`MCSL2_API/__init__.py` 把能力组织成 `API`、`Event` 与 `core`）。

### 7.1 顶层导入

```python
from MCSL2_API import API, Event, core
from MCSL2_API import Plugin, PluginContext, PluginManifest, Context
from MCSL2_API.models import ServerInfo, ServerStatus, State, LogEvent, ServerExitEvent
```

### 7.2 API（Facade 命名空间）

* `API.server`: [ServerAdapter](MCSL2_API/adapters/server.py)
* `API.ui`: [UIAdapter](MCSL2_API/adapters/ui.py)
* `API.download`: [DownloadAdapter](MCSL2_API/adapters/download.py)
* `API.interaction`: 交互提供者（注入 Window 后优先使用 GUI 交互）
* `API.backend_window`: 当前注入的 Window（可能为 None）
* `API.unsafe_access`: [UnsafeAccess](MCSL2_API/core.py)（进阶）

### 7.3 Event（事件命名空间）

事件类型：
* `Event.Log`：等价 `MCSL2_API.models.LogEvent`
* `Event.ServerExit`：等价 `MCSL2_API.models.ServerExitEvent`
* `Event.ServerStop`：当前版本等价 `ServerExitEvent`（占位别名）

订阅：
* `@Event.on(EventType, background=True)`：订阅指定事件类型
* `Event.subscribe(fn=None, event_type=None, background=True, priority=0)`：可推断事件类型（需要参数类型注解）

优先级：
* `priority` 值越大越先执行

### 7.4 core（APICore 单例与工具函数）

`core` 是 `APICore()` 的单例实例。

常用方法：
* `core.inject_backend(backend_window)`
* `core.set_interaction(provider)`
* `core.get_bridge(server_name)`
* `core.get_mcsl2_version() -> str`
* `core.get_ai_analyzer_config() -> dict`
* `core.get_ai_api_key(model: str | None = None) -> str`
* `core.ai_analyze_plugin_error(error_text: str) -> str`
* `core.load_nested_plugin(plugin_name, plugins_dir=r".\Plugins", package_prefix="Plugins", entry_attr_names=None) -> object | None`

通过 `MCSL2_API` 顶层也暴露了别名函数：
* `get_mcsl2_version`
* `get_ai_analyzer_config`
* `get_ai_api_key`
* `ai_analyze_plugin_error`
* `load_nested_plugin`

### 7.5 API.server（ServerAdapter）

读取与查找：
* `API.server.list() -> list[ServerInfo]`
* `API.server.get(server_name: str) -> ServerInfo | None`

状态：
* `API.server.status(server_name: str) -> ServerStatus`
* `API.server.status_async(server_name: str) -> Future[ServerStatus]`

控制（对外推荐异步版本）：
* `API.server.start(server_name: str) -> Future[bool]`
* `API.server.stop(server_name: str, force: bool = False) -> Future[bool]`
* `API.server.restart(server_name: str) -> Future[bool]`
* `API.server.command(server_name: str, command: str) -> Future[bool]`

内部同步版本（通常不直接用）：
* `API.server.start_server(server_name: str) -> bool`
* `API.server.stop_server(server_name: str, force: bool = False) -> bool`
* `API.server.restart_server(server_name: str) -> bool`
* `API.server.command_server(server_name: str, command: str) -> bool`

其他：
* `API.server.accept_eula(server_name: str) -> bool`

### 7.6 API.ui（UIAdapter）

解析与注入：
* `API.ui.resolve(path: str) -> object`
* `API.ui.add_to_layout(layout_path: str, widget: QWidget) -> QWidget`

常用控件：
* `API.ui.add_button(layout_path: str, text: str, on_click=None, primary: bool = True) -> QWidget`
* `API.ui.add_line_edit(layout_path: str, placeholder: str = "", text: str = "", on_change=None) -> QWidget`

页面与窗口：
* `API.ui.add_page(title: str, widget: QWidget, icon=None, position=None, object_name: str | None = None) -> QWidget`
* `API.ui.open_window(widget: QWidget, title: str = "MCSL2_API", modal: bool = False, parent_path: str = "") -> QDialog`

其他：
* `API.ui.set_text(widget_path: str, text: str) -> None`

### 7.7 API.download（DownloadAdapter）

* `API.download.start_task(url: str, file_path: str | None = None, file_name: str | None = None, file_size: int = -1, extra_data: tuple | None = None) -> object`

### 7.8 线程工具（utils.threading）

* `MCSL2_API.utils.threading.is_ui_thread() -> bool`
* `MCSL2_API.utils.threading.run_on_ui_thread(func, *args, wait: bool = True, **kwargs) -> T | Future[T]`
* `core.threading.submit(fn, *args, **kwargs) -> Future`

### 7.9 模型（models）

* `ServerInfo(name, index, core_file_name=None, java_path=None, server_type=None, extra=dict)`
* `ServerStatus(name, state: State, pid=None, exit_code=None, players=None)`
* `State`: `STOPPED/STARTING/RUNNING/CRASHED`
* `LogEvent(server_name, content, ts)`
* `ServerExitEvent(server_name, exit_code, ts)`

注：如果环境安装了 pydantic，这些模型为 `BaseModel`；否则为 `dataclass`。

---

## 8. 故障排查

### 8.1 导入错误：`ModuleNotFoundError: No module named 'MCSL2_API'`

* 终端用户无 pip 环境：请使用 Vendor 模式并确保入口文件顶部注入 `_vendor` 到 `sys.path`
* 开发者环境：请确认安装的是 `mcsl2-api`（不是 `MCSL2_API`）

### 8.2 收不到 `Event.Log` / `Event.ServerExit`

* 确保已调用 `core.events.install_hooks()`
* 如果服务器不是通过 MCSL2 的标准启动流程启动，可能无法拿到 bridge 信号

### 8.3 UI 注入路径无效

* 路径来自 `Window` 上的对象树（版本变动会影响命名）
* 可用下面方式辅助探索：

```python
win = API.ui.resolve("")
print([attr for attr in dir(win) if "Interface" in attr])
```
