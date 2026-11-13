from pathlib import Path
from xml.etree import ElementTree

from python_qt_binding import QtCore, QtWidgets


class DraftEditorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        for label, tip, callback in (
            ('New', 'Clear the current XML draft.', self.new_draft),
            ('Load XML', 'Load XML into the isolated draft.', self.load_draft),
            ('Save XML', 'Save the current draft to an XML file.', self.save_draft),
            ('Check XML', 'Check XML well-formedness and the Plan root; this does not validate or dispatch the plan.', self.check_xml),
        ):
            button = QtWidgets.QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.status = QtWidgets.QLabel('XML draft only. Graph editing, plan validation, and dispatch are unavailable.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlaceholderText('Enter or load Fabric XML.')
        self.editor.setToolTip('Edit an isolated XML draft. Changes do not affect the live plan.')
        self.editor.textChanged.connect(self._draft_changed)
        layout.addWidget(self.editor, stretch=1)

    def _draft_changed(self):
        self.status.setText('Draft changed. XML syntax has not been checked; the plan has not been validated.')

    def confirm_discard(self):
        if not self.editor.document().isModified():
            return True
        return QtWidgets.QMessageBox.question(
            self, 'Discard draft changes?', 'Discard unsaved XML draft changes?',
            QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        ) == QtWidgets.QMessageBox.Discard

    def prepare_for_plugin_shutdown(self):
        message = 'rqt is removing this plugin and cannot cancel the removal. Save or discard the unsaved XML draft.'
        while self.editor.document().isModified():
            choice = QtWidgets.QMessageBox.warning(
                self, 'Unsaved XML draft', message,
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard,
                QtWidgets.QMessageBox.Save,
            )
            if choice == QtWidgets.QMessageBox.Discard:
                self.editor.document().setModified(False)
            elif choice == QtWidgets.QMessageBox.Save and not self.save_draft():
                message = 'The draft was not saved. Save it or discard it before rqt removes the plugin.'

    def new_draft(self):
        if self.confirm_discard():
            self.editor.clear()
            self.editor.document().setModified(False)
            self.status.setText('New XML draft. Graph editing, plan validation, and dispatch are unavailable.')

    def load_draft(self):
        if not self.confirm_discard():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load XML draft', '', 'XML files (*.xml);;All files (*)')
        if not path:
            return
        try:
            text = Path(path).read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            self.status.setText(f'Could not load XML draft: {exc}')
            return
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.status.setText(f'Loaded draft: {path}. The plan has not been validated.')

    def save_draft(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save XML draft', '', 'XML files (*.xml);;All files (*)')
        if not path:
            return False
        try:
            data = self.editor.toPlainText().encode('utf-8')
        except UnicodeError as exc:
            self.status.setText(f'Could not save XML draft: {exc}')
            return False
        output = QtCore.QSaveFile(path)
        if not output.open(QtCore.QIODevice.WriteOnly):
            self.status.setText(f'Could not save XML draft: {output.errorString()}')
            return False
        if output.write(data) != len(data):
            error = output.errorString()
            output.cancelWriting()
            self.status.setText(f'Could not save XML draft: {error}')
            return False
        if not output.commit():
            self.status.setText(f'Could not save XML draft: {output.errorString()}')
            return False
        self.editor.document().setModified(False)
        self.status.setText(f'Saved draft: {path}. The plan has not been validated.')
        return True

    def check_xml(self):
        try:
            root = ElementTree.fromstring(self.editor.toPlainText())
        except ElementTree.ParseError as exc:
            self.status.setText(f'XML syntax error: {exc}')
            return
        if root.tag != 'Plan':
            self.status.setText('XML must have a Plan root element. The plan has not been validated.')
            return
        self.status.setText('XML is well-formed with a Plan root. Fabric syntax and capabilities have not been validated.')