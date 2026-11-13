from __future__ import annotations

import argparse

from qt_gui.plugin import Plugin

from fabric_experience_gui.app import InspectorWidget


class ExperienceInspectorPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.setObjectName('ExperienceInspectorPlugin')

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--db-path', default='')
        parser.add_argument('--audit-root', default='')
        known_args, _ = parser.parse_known_args(context.argv())

        self._widget = InspectorWidget(
            initial_db_path=known_args.db_path,
            initial_audit_root=known_args.audit_root,
        )
        self._widget.setObjectName('ExperienceInspectorWidget')

        if context.serial_number() > 1:
            self._widget.setWindowTitle(f'Fabric Experience GUI ({context.serial_number()})')

        context.add_widget(self._widget)

    def shutdown_plugin(self):
        self._widget.draft_editor.prepare_for_plugin_shutdown()
        self._widget.close()

    def save_settings(self, plugin_settings, instance_settings):
        instance_settings.set_value('db_path', self._widget.current_db_path())
        instance_settings.set_value('audit_root', self._widget.current_audit_root())

    def restore_settings(self, plugin_settings, instance_settings):
        del plugin_settings
        db_path = instance_settings.value('db_path', '')
        audit_root = instance_settings.value('audit_root', '')
        if db_path:
            self._widget.set_db_path(db_path)
            self._widget.load_database(db_path)
        if audit_root:
            self._widget.set_audit_root(audit_root)
            self._widget.load_prompt_audits()