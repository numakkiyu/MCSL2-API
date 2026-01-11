# MCSL2_API 调用文档

本文按“我想做什么”来组织，覆盖 MCSL2_API 的主要调用方式、返回值形态与线程注意事项。

## 目录

- [快速索引](#快速索引)
- [全局入口：API / Event / core](#全局入口api--event--core)
- [服务器 API（API.server）](#服务器-apiapiserver)
- [下载 API（API.download）](#下载-apiapidownload)
- [事件 API（Event/core.events）](#事件-apieventcoreevents)
- [插件标准入口（Plugin）](#插件标准入口plugin)
- [异常隔离（guard）](#异常隔离guard)
- [数据模型（models）](#数据模型models)

## 快速索引

常用 import：

```python
from MCSL2_API import API, Event, core
from MCSL2_API import Plugin, PluginContext, PluginManifest
```

常用动作：

- 注入 MCSL2 后端窗口：`core.inject_backend(Window())`
- 安装服务器启动 Hook：`core.events.install_hooks()`
- 启动服务器（推荐异步）：`API.server.start("生存服") -> Future[bool]`
- 停止服务器（推荐异步）：`API.server.stop("生存服") -> Future[bool]`
- 订阅服务器退出事件：`@Event.on(Event.ServerExit)`

## 全局入口：API / Event / core

这些符号都由 [`__init__.py`] 暴露。

### core（APICore 单例）

`core` 是 [`APICore`] 的单例实例，提供：

- `core.inject_backend(backend_window) -> None`
- `core.backend_window -> Any | None`
- `core.interaction -> InteractionProvider`
- `core.set_interaction(provider) -> None`
- `core.threading -> ThreadManager`
- `core.events -> EventBus`
- `core.unsafe_access -> UnsafeAccess`

注入 backend 的典型用法（MCSL2 GUI 环境）：

```python
from MCSL2Lib.windowInterface import Window
from MCSL2_API import core

core.inject_backend(Window())
```

### API（Facade）

`API` 是一个组合入口，主要暴露：

- `API.server: ServerAdapter`
- `API.download: DownloadAdapter`
- `API.interaction` / `API.backend_window` / `API.unsafe_access`

### Event（事件命名空间）

`Event` 是一个“命名空间对象”，提供：

- `Event.Log`、`Event.ServerExit`、`Event.ServerStop`：事件类型
- `Event.on(event_type, *, background=True)`：装饰器（不带 priority）
- `Event.subscribe(fn=None, *, event_type=None, background=True, priority=0)`：装饰器（支持 priority 与自动推断 event_type）

## 服务器 API（API.server）

实现见 [`adapters/server.py`]。

### 读取服务器列表

```python
servers = API.server.list()          # -> list[ServerInfo]
server = API.server.get("生存服")    # -> ServerInfo | None
```

- 需要 MCSL2Lib 环境（内部使用 `MCSL2Lib.utils.readGlobalServerConfig`）
- 返回的 `ServerInfo` 为标准模型（见 [数据模型](#数据模型models)）

### 查询运行状态

```python
status = API.server.status("生存服")       # -> ServerStatus
fut = API.server.status_async("生存服")    # -> Future[ServerStatus]
```

状态的判断依赖于已注册的 `bridge`（通常由启动 Hook 或 `start_server` 在启动成功后注册）。

### 启动服务器

推荐使用异步入口：

```python
fut = API.server.start("生存服")  # -> Future[bool]
ok = fut.result()
```

同步版本（供内部或你自己放到后台线程时使用）：

```python
ok = API.server.start_server("生存服")  # -> bool
```

注意事项：

- `start(...)` 是线程池异步调用，不会阻塞 UI
- 真实启动过程会在 UI 线程执行（封送到 `run_on_ui_thread`）
- 启动前会尝试 `core.events.install_hooks()`，并在成功拿到 bridge 后立即 `hook_bridge(...)`
- 若返回 EULA 对象（未同意），会返回 False，并通过 `interaction.notify(...)` 提示

### EULA

```python
ok = API.server.accept_eula("生存服")  # -> bool
```

### 停止/重启/发送命令

这些都提供同步与异步入口：

```python
API.server.stop("生存服")                    # -> Future[bool]
API.server.stop_server("生存服", force=False) # -> bool

API.server.restart("生存服")                  # -> Future[bool]
API.server.restart_server("生存服")           # -> bool

ok = API.server.command_server("生存服", "say hello")  # -> bool
```

实现细节：

- 实际调用 `bridge.stopServer()/haltServer()/restartServer()/sendCommand(...)` 并封送回 UI 线程
- 如果找不到 bridge，会返回 False 并提示

## 下载 API（API.download）

实现见 [`adapters/download.py`]。

```python
task = API.download.start_task(
    "https://example.com/file.zip",
    file_path="C:/Downloads",
    file_name="file.zip",
    file_size=-1,
)
```

- 该函数会尝试在 UI 线程创建 `MCSL2Lib.ProgramControllers.downloadController.DownloadTask`
- 成功时返回 task 对象；失败返回 None，并通过 `interaction.notify(...)` 提示

## 事件 API（Event/core.events）

实现见 [`events/bus.py`]。

### 订阅事件（简写：Event.on）

```python
from MCSL2_API import Event


@Event.on(Event.Log)
def on_log(e) -> None:
    print(e.content)
```

`Event.on(...)` 默认 `background=True`，回调在后台线程执行。

### 订阅事件（高级：Event.subscribe / core.events.on）

如果你需要 **priority** 或 **自动推断 event_type**：

```python
from MCSL2_API import Event


@Event.subscribe(priority=50)
def on_exit(e: Event.ServerExit) -> None:
    print(e.exit_code)
```

等价于直接用 `core.events.subscribe(...)` / `core.events.on(...)`。

### 安装 Hook

要把 MCSL2 的服务器启动结果（bridge）与信号转换为事件，需要安装 Hook：

```python
from MCSL2_API import core

core.events.install_hooks()
```

Hook 目标：`MCSL2Lib.ServerControllers.processCreator.ServerLauncher.start`。当 start 返回 bridge 时，会自动连接 `serverLogOutput/serverClosed` 并派发：

- `LogEvent(server_name, content, ts)`
- `ServerExitEvent(server_name, exit_code, ts)`

### 可取消事件（约定）

`EventBus.emit(...)` 会在每次回调前检查 `event.cancelled`。因此，只要你的事件对象具有该属性，就可用于“取消后续回调”的控制流：

```python
from MCSL2_API.events.bus import Cancellable


class MyEvent(Cancellable):
    pass
```

## 插件标准入口（Plugin）

实现见 [`plugin.py`]。

### 生命周期签名

- `on_load(context: PluginContext) -> None`
- `on_enable(context: PluginContext) -> None`
- `on_disable(context: PluginContext) -> None`

`PluginContext` 主要字段：

- `context.core: APICore`
- `context.manifest: PluginManifest`
- `context.plugin_name: str`
- `context.backend_window`（透传 core.backend_window）
- `context.interaction`（透传 core.interaction）

### 事件订阅（类内写法）

```python
from MCSL2_API import Plugin, Event


class P(Plugin):
    @Plugin.subscribe(priority=10)
    def on_exit(self, e: Event.ServerExit) -> None:
        ...
```

在 `Plugin.export(...)` 执行的生命周期回调中，会扫描并自动注册这些订阅方法。

### 兼容旧加载器：export

```python
PluginEntry = P.export(manifest=manifest)
```

- 旧加载器只要能拿到 `PluginEntry` 即可调用
- 导出的旧入口已做异常隔离（见 [异常隔离](#异常隔离guard)）

## 异常隔离（guard）

实现见 [`safety.py`]。

```python
from MCSL2_API.safety import guard


safe_fn = guard("my-plugin", fn)
safe_fn()
```

特点：

- 捕获所有异常，优先调用 `MCSL2Lib.utils.MCSL2Logger` 输出
- 失败时退化为 stdout 打印
- 返回值会变成 `Optional[T]`（异常时返回 None）

## 数据模型（models）

实现见 [`models.py`]。

常用模型：

- `ServerInfo`：服务器元数据（name/index/core_file_name/java_path/server_type/extra）
- `ServerStatus`：运行状态（name/state/pid/exit_code/players）
- `State`：`STOPPED/STARTING/RUNNING/CRASHED`
- `LogEvent`：`server_name/content/ts`
- `ServerExitEvent`：`server_name/exit_code/ts`

是否启用 Pydantic：

- 若环境中安装了 `pydantic`，这些模型会以 `BaseModel` 形式提供更强校验
- 否则自动降级为 `dataclass`（仍保持字段与语义一致）

