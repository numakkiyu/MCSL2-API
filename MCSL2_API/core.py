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
import json
from os import path as osp
import traceback
import threading
from typing import Any
from typing import Optional

from .events.bus import EventBus
from .interaction import HeadlessInteraction
from .interaction import InteractionProvider
from .interaction import FluentInteraction
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
                    try:
                        self.interaction = FluentInteraction(parent=backend_window)
                    except Exception:
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

    def get_mcsl2_version(self) -> str:
        try:
            from MCSL2Lib import MCSL2VERSION  # type: ignore

            return str(MCSL2VERSION or "")
        except Exception:
            return ""

    def _read_config_json(self) -> dict:
        try:
            from MCSL2Lib.ProgramControllers.settingsController import cfg  # type: ignore

            return {
                "AIAnalyzer": {
                    "provider": cfg.get(cfg.aiAnalyzeProvider),
                    "baseUrl": cfg.get(cfg.aiAnalyzeBaseUrl),
                    "apiKey": cfg.get(cfg.aiAnalyzeApiKey),
                    "apiKeys": cfg.get(cfg.aiAnalyzeApiKeys),
                    "model": cfg.get(cfg.aiAnalyzeModel),
                    "prompt": cfg.get(cfg.aiAnalyzePrompt),
                }
            }
        except Exception:
            pass

        try:
            with open(r".\MCSL2\MCSL2_Config.json", "r", encoding="utf-8") as f:
                data = json.loads(f.read() or "{}")
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_ai_analyzer_config(self) -> dict:
        cfg = self._read_config_json().get("AIAnalyzer") or {}
        return cfg if isinstance(cfg, dict) else {}

    def get_ai_api_key(self, model: Optional[str] = None) -> str:
        cfg = self.get_ai_analyzer_config()
        api_key = (cfg.get("apiKey") or "").strip()
        api_keys_raw = (cfg.get("apiKeys") or "").strip()
        if api_keys_raw:
            try:
                obj = json.loads(api_keys_raw)
                if isinstance(obj, dict):
                    m = (model or cfg.get("model") or "").strip()
                    mk = (obj.get(m) or "").strip() if m else ""
                    if mk:
                        return mk
                    return "" if obj else api_key
            except Exception:
                return api_key
        return api_key

    def ai_analyze_plugin_error(self, error_text: str) -> str:
        if self.get_mcsl2_version() != "2.3.0.0":
            raise RuntimeError("仅支持 MCSL2 2.3.0.0 的 AI 报错分析接口。")

        cfg = self.get_ai_analyzer_config()
        base_url = str(cfg.get("baseUrl") or "https://api.openai.com/v1").strip()
        model = str(cfg.get("model") or "").strip()
        api_key = self.get_ai_api_key(model=model)
        if not api_key:
            raise RuntimeError("未配置 AIAnalyzer.apiKey/apiKeys，无法进行 AI 报错分析。")
        if not model:
            raise RuntimeError("未配置 AIAnalyzer.model，无法进行 AI 报错分析。")

        try:
            from openai import OpenAI  # type: ignore
        except Exception:
            raise RuntimeError("缺少 openai 依赖，无法进行 AI 报错分析。")

        prompt = (
            "你是一位资深 Python 桌面应用插件开发与调试专家。\n"
            "请只基于用户提供的异常信息进行诊断。\n"
            "输出必须是纯文本，不要 Markdown，不要 JSON。\n"
            "必须覆盖：核心原因、触发点、修复步骤（按优先级）、可选增强建议。\n"
            "请用中文回答。\n"
        )

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": (error_text or "").strip()},
                ],
                max_tokens=900,
                temperature=0.2,
            )
        except Exception as e:
            return "AI 请求异常：\n" + str(e) + "\n\n" + traceback.format_exc()

        try:
            choices = getattr(resp, "choices", None) or []
            if not choices:
                return "AI 返回空响应（choices 为空）。"
            msg = getattr(choices[0], "message", None)
            text = getattr(msg, "content", None) if msg is not None else None
            return (text or "").strip() or "AI 返回空内容。"
        except Exception:
            return "AI 响应解析失败：\n" + traceback.format_exc()

    def _show_message_box(self, title: str, content: str) -> None:
        try:
            from .utils.threading import run_on_ui_thread
        except Exception:
            run_on_ui_thread = None

        def _do() -> None:
            try:
                from PyQt5.QtWidgets import QApplication  # type: ignore
                from qfluentwidgets import MessageBox  # type: ignore
            except Exception:
                try:
                    self.interaction.notify(content, title=title, level="error")
                except Exception:
                    return
                return

            parent = None
            try:
                app = QApplication.instance()
                parent = None if app is None else app.activeWindow()
            except Exception:
                parent = None

            try:
                w = MessageBox(title, content, parent)
                try:
                    w.yesButton.setText("了解")
                except Exception:
                    pass
                try:
                    w.cancelButton.setParent(None)  # type: ignore[attr-defined]
                    w.cancelButton.deleteLater()  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    w.exec()
                except Exception:
                    w.exec_()
            except Exception:
                try:
                    self.interaction.notify(content, title=title, level="error")
                except Exception:
                    return

        try:
            if run_on_ui_thread is None:
                _do()
                return
            run_on_ui_thread(_do, wait=False)
        except Exception:
            try:
                _do()
            except Exception:
                return

    def load_nested_plugin(
        self,
        plugin_name: str,
        *,
        plugins_dir: str = r".\Plugins",
        package_prefix: str = "Plugins",
        entry_attr_names: Optional[list[str]] = None,
    ) -> Optional[Any]:
        name = str(plugin_name or "").strip()
        if not name:
            return None

        file_path = osp.join(str(plugins_dir), name, f"{name}.py")
        module_name = f"{package_prefix}.{name}.{name}"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            compile(source, file_path, "exec")
        except SyntaxError:
            self._show_message_box(f'插件 "{name}" 语法错误', traceback.format_exc())
            return None
        except FileNotFoundError:
            self._show_message_box(f'插件 "{name}" 不存在', f"未找到插件文件：\n{file_path}")
            return None
        except Exception:
            self._show_message_box(f'读取插件 "{name}" 失败', traceback.format_exc())
            return None

        try:
            import importlib

            module = importlib.import_module(module_name)
        except Exception:
            self._show_message_box(f'加载插件 "{name}" 失败', traceback.format_exc())
            return None

        candidates = []
        if entry_attr_names:
            candidates.extend([str(x) for x in entry_attr_names if str(x).strip()])
        candidates.extend([name, "PluginEntry", "plugin", "PLUGIN"])

        for attr in candidates:
            try:
                if hasattr(module, attr):
                    return getattr(module, attr)
            except Exception:
                continue

        return module
