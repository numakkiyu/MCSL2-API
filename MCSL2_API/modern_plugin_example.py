from __future__ import annotations

from MCSL2_API import Event
from MCSL2_API import Plugin
from MCSL2_API import PluginContext
from MCSL2_API import PluginManifest
from MCSL2_API import core


manifest = PluginManifest(
    id="auto-backup",
    version="1.0.0",
    dependencies=["mcsl-core>=2.0"],
)


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
