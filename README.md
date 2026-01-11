# MCSL2_API

面向 **MCSL2 插件开发者** 的轻量 API 层：把 MCSL2 的旧式调用封装成更稳定、可类型化、线程安全的入口，并提供事件总线与插件标准化入口（同时兼容旧加载器）。

## 目录

- [目标](#目标)
- [特性](#特性)
- [目录结构](#目录结构)
- [安装与导入](#安装与导入)
- [快速上手](#快速上手)
- [事件系统](#事件系统)
- [现代插件标准（Plugin）](#现代插件标准plugin)
- [线程模型与 UI 封送](#线程模型与-ui-封送)
- [交互层（Interaction）](#交互层interaction)
- [常见问题](#常见问题)

## 目标

- **对插件侧友好**：尽量减少“魔法变量名/隐式约定”，提供更清晰的入口与类型。
- **对宿主非侵入**：不修改 MCSL2Lib 源码，仅通过封装与 Hook 完成能力扩展。
- **更安全**：隔离插件异常，避免插件报错导致主程序崩溃。

## 特性

- 标准化插件入口：[`Plugin`] + 生命周期 `on_load/on_enable/on_disable`
- 兼容旧加载器：`Plugin.export(...)` 生成旧系统可识别的 `PluginEntry`
- 元数据模型：[`PluginManifest`]（优先使用 Pydantic，缺省自动降级） 
- 事件总线：[`EventBus`]（支持优先级、可取消事件、默认后台派发）
- Facade API：`API.server` / `API.download`（线程安全、返回 Future 的异步入口）
- UI/Headless 交互抽象：[`InteractionProvider`]

## 目录结构

```text
MCSL2_API/
  __init__.py              对外入口：API / Event / core / Plugin / PluginManifest / Context
  core.py                  APICore：运行时容器，持有事件/线程池/交互/bridge
  plugin.py                Plugin/PluginContext 与旧加载器兼容导出
  manifest.py              PluginManifest（Pydantic 可选）
  safety.py                guard：异常隔离装饰器
  models.py                对外数据模型与事件载体
  interaction.py           notify 抽象与 Qt/Headless 实现
  adapters/
    server.py              服务器相关 Facade（start/stop/restart/status 等）
    download.py            下载任务 Facade（DownloadTask）
  events/
    bus.py                 事件总线 + 启动 Hook（ServerLauncher.start）
  utils/
    threading.py           UI 封送与线程池工具
  modern_plugin_example.py 现代插件示例（Plugin + export）
  example_agent_plugin.py  老式插件示例（Event + API + enable(...)）
```

## 安装与导入

此仓库内为可编辑安装/直接导入均可用的结构，常见方式：

- **作为仓库内模块使用**：确保 `MCSL2_API/` 在 Python 路径中（MCSL2 工程运行时通常满足）。
- **作为独立包安装（可选）**：在 `MCSL2_API/` 下执行可编辑安装。

依赖见 [pyproject.toml]

- 必需：`PyQt5>=5.15`
- 可选：`pydantic`（用于更强的模型校验与提示）

## 快速上手

### 1) 在 MCSL2 插件环境里使用（推荐）

插件在 MCSL2 环境运行时，可以注入 backend（Window 单例），然后使用 API 与事件。

```python
from __future__ import annotations

from MCSL2_API import API, Event, core


@Event.on(Event.ServerExit)
def on_exit(e) -> None:
    API.server.start(e.server_name)


def enable(window_instance, server_name: str) -> None:
    core.inject_backend(window_instance)
    core.events.install_hooks()
    API.server.start(server_name)
```

完整示例见

### 2) 使用现代插件标准（Plugin）

```python
from __future__ import annotations

from MCSL2_API import Event, Plugin, PluginContext, PluginManifest, core


manifest = PluginManifest(id="auto-backup", version="1.0.0", dependencies=["mcsl-core>=2.0"])


class AutoBackupPlugin(Plugin):
    def on_load(self, context: PluginContext) -> None:
        context.interaction.notify("备份插件已加载", title=manifest.id, level="info")

    def on_enable(self, context: PluginContext) -> None:
        context.interaction.notify("备份插件已启动！", title=manifest.id, level="info")

    def on_disable(self, context: PluginContext) -> None:
        context.interaction.notify("备份插件已停止", title=manifest.id, level="info")

    @Plugin.subscribe(priority=10)
    def on_server_stop(self, event: Event.ServerStop) -> None:
        core.interaction.notify("服务器停止，开始备份...", title=manifest.id, level="info")


PluginEntry = AutoBackupPlugin.export(manifest=manifest)
```

完整示例见

## 事件系统

事件总线入口有两层：

- 对插件侧：`Event.on(Event.Log)` / `Event.on(Event.ServerExit)`（语法更短）
- 对高级用法：`core.events.on(...)` / `core.events.subscribe(...)`（支持显式 event_type、priority 等）

### 内置事件类型

`Event` 命名空间当前提供：

- `Event.Log` → [`LogEvent`]
- `Event.ServerExit` / `Event.ServerStop` → [`ServerExitEvent`]

### 安装 Hook（把 MCSL2 信号转事件）

要捕获服务器日志/退出事件，需要安装启动 Hook：

```python
from MCSL2_API import core

core.events.install_hooks()
```

通常配合 `core.inject_backend(window_instance)` 使用（保证 Qt 环境已就绪）。

### 优先级与可取消事件

- `priority` 越大，越先执行。
- 事件对象只要拥有 `cancelled: bool` 属性，并在需要时将其设为 True，就会阻止后续回调继续执行（见 [`EventBus.emit`]的行为）。

## 现代插件标准（Plugin）

核心类与约定：

- `Plugin.manifest: PluginManifest`
- `on_load(context: PluginContext) -> None`
- `on_enable(context: PluginContext) -> None`
- `on_disable(context: PluginContext) -> None`

兼容旧加载器的关键点：

- `Plugin.export(manifest=...)` 会把旧加载器需要的对象写入调用模块的全局变量 `PluginEntry`
- 导出的旧入口会自动加上异常隔离（见 [`guard`]）

## 线程模型与 UI 封送

本库的基本约束：

- **耗时操作**：默认走线程池（`core.threading.submit(...)` / API 的异步入口）
- **触碰 Qt 对象**：必须封送到 UI 线程（`run_on_ui_thread(...)`）

相关实现：

- [`utils/threading.py`]
- 服务器启动过程会封送到 UI 线程执行（见 [`ServerAdapter.start_server`]

## 交互层（Interaction）

API 代码不直接弹窗，而是调用：

```python
core.interaction.notify("文本", title="标题", level="info")
```

默认是 `HeadlessInteraction`（打印到 stdout）；注入 backend 后，会自动尝试切换为 `QtInteraction`。

实现与扩展点见 [interaction.py]。

## 常见问题

### 1) 调用 `run_on_ui_thread` 报 Qt 未初始化

说明当前没有创建 Qt Application，或不在 MCSL2 GUI 环境中运行。通常在 MCSL2 插件环境内使用，并先 `core.inject_backend(Window())` 可避免。

### 2) 收不到 Log/ServerExit 事件

确保：

- 已调用 `core.events.install_hooks()`
- 服务器是通过 MCSL2 的 `ServerLauncher.start` 启动（Hook 目标见 [`EventBus.install_hooks`]）

