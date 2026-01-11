"""
MCSL2_API 数据模型层。

该模块只定义“标准化的数据结构”，用于：
- API 对外返回（避免直接暴露 MCSL2 内部 dict 结构）
- 事件总线事件载体（跨线程传递的数据必须是纯数据对象）

设计约束：
- 这里不允许 import MCSL2Lib（避免在无 MCSL2 环境下导入失败）
- 不依赖额外第三方库，确保在 MCSL2 默认依赖集下可用
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING

try:
    from pydantic import BaseModel  # type: ignore
    from pydantic import Field  # type: ignore

    _HAS_PYDANTIC = True
except Exception:
    BaseModel = object  # type: ignore
    Field = None  # type: ignore
    _HAS_PYDANTIC = False


class State(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"


ServerStatusState = State


if _HAS_PYDANTIC:

    class ServerInfo(BaseModel):  # type: ignore[misc]
        name: str
        index: int
        core_file_name: Optional[str] = None
        java_path: Optional[str] = None
        server_type: Optional[str] = None
        extra: Dict[str, Any] = Field(default_factory=dict)  # type: ignore[call-arg]

    class ServerStatus(BaseModel):  # type: ignore[misc]
        name: str
        state: State
        pid: Optional[int] = None
        exit_code: Optional[int] = None
        players: Optional[int] = None

    class LogEvent(BaseModel):  # type: ignore[misc]
        server_name: str
        content: str
        ts: float

    class ServerExitEvent(BaseModel):  # type: ignore[misc]
        server_name: str
        exit_code: int
        ts: float

else:

    @dataclass(frozen=True, slots=True)
    class ServerInfo:
        name: str
        index: int
        core_file_name: Optional[str] = None
        java_path: Optional[str] = None
        server_type: Optional[str] = None
        extra: Dict[str, Any] = field(default_factory=dict)

    @dataclass(frozen=True, slots=True)
    class ServerStatus:
        name: str
        state: State
        pid: Optional[int] = None
        exit_code: Optional[int] = None
        players: Optional[int] = None

    @dataclass(frozen=True, slots=True)
    class LogEvent:
        server_name: str
        content: str
        ts: float

    @dataclass(frozen=True, slots=True)
    class ServerExitEvent:
        server_name: str
        exit_code: int
        ts: float

if TYPE_CHECKING:
    from typing import Type

    ModelType = Type[BaseModel]  # noqa: F401
