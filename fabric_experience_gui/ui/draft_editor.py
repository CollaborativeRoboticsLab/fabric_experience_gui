from pathlib import Path
from xml.etree import ElementTree

from python_qt_binding import QtCore, QtWidgets

from fabric_experience_gui.draft_model import DraftModel
from fabric_experience_gui.ui.fabric_graph_requests import FabricGraphRequests


class DraftEditorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.runnable_pairs = ()
        self.requests = FabricGraphRequests(self)
        self.requests.capture_ready.connect(self._runnable_ready)
        self.requests.failed.connect(self._runnable_failed)
        self.requests.busy_changed.connect(self._runnable_busy_changed)
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        for label, tip, callback in (
            ('New', 'Clear the current XML draft.', self.new_draft),
            ('Load XML', 'Load XML into the isolated draft.', self.load_draft),
            ('Save XML', 'Save the current draft to an XML file.', self.save_draft),
            ('Check XML', 'Check XML well-formedness and the Plan root; this does not validate or dispatch the plan.', self.check_xml),
            ('Inspect Structure', 'Inspect the supported draft structure without validating or dispatching it.', self.inspect_structure),
        ):
            button = QtWidgets.QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        runnable_controls = QtWidgets.QHBoxLayout()
        self.refresh_runnable_button = QtWidgets.QPushButton('Refresh Runnables')
        self.refresh_runnable_button.setToolTip('Request available interface and provider pairs from capabilities2.')
        self.refresh_runnable_button.clicked.connect(self.refresh_runnables)
        runnable_controls.addWidget(self.refresh_runnable_button)
        self.runnable_combo = QtWidgets.QComboBox()
        self.runnable_combo.setToolTip('Select a discovered interface and provider for the selected runner.')
        self.runnable_combo.currentIndexChanged.connect(self._update_apply_state)
        runnable_controls.addWidget(self.runnable_combo, stretch=1)
        self.apply_runnable_button = QtWidgets.QPushButton('Set Runner')
        self.apply_runnable_button.setToolTip('Replace the selected draft runner interface and provider without dispatching.')
        self.apply_runnable_button.clicked.connect(self.apply_runnable)
        self.apply_runnable_button.setEnabled(False)
        runnable_controls.addWidget(self.apply_runnable_button)
        layout.addLayout(runnable_controls)
        self.runnable_status = QtWidgets.QLabel('Runnable specifications not refreshed.')
        self.runnable_status.setWordWrap(True)
        layout.addWidget(self.runnable_status)
        self.status = QtWidgets.QLabel('Isolated draft. Graph layout editing, plan validation, and dispatch are unavailable.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlaceholderText('Enter or load Fabric XML.')
        self.editor.setToolTip('Edit an isolated XML draft. Changes do not affect the live plan.')
        self.editor.textChanged.connect(self._draft_changed)
        self.structure = QtWidgets.QTreeWidget()
        self.structure.setHeaderLabels(['Draft structure', 'Interface / provider'])
        self.structure.setToolTip('Read-only structure from the current XML draft; runner parameters are XML attributes.')
        self.structure.itemSelectionChanged.connect(self._update_apply_state)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.structure)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

    def _draft_changed(self):
        self.model = None
        self.structure.clear()
        self._update_apply_state()
        self.status.setText('Draft changed. XML syntax has not been checked; the plan has not been validated.')

    def confirm_discard(self):
        if not self.editor.document().isModified():
            return True
        choice = QtWidgets.QMessageBox.question(
            self, 'Unsaved XML draft', 'Save the unsaved XML draft changes?',
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        if choice == QtWidgets.QMessageBox.Save:
            return self.save_draft()
        return choice == QtWidgets.QMessageBox.Discard

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
            self.status.setText('New XML draft. Graph layout editing, plan validation, and dispatch are unavailable.')

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

    def inspect_structure(self):
        self.model = None
        self.structure.clear()
        try:
            model = DraftModel(self.editor.toPlainText())
        except ValueError as exc:
            self.status.setText(f'Cannot inspect draft structure: {exc} The plan has not been validated.')
            return

        def add_node(parent, node):
            attributes = dict(node.attributes)
            if node.kind == 'Control':
                label = f'Control: {attributes["type"]}'
            else:
                label = node.kind
            identity = ''
            if node.kind == 'Runner':
                identity = f'{attributes["interface"]} / {attributes["provider"]}'
            item = QtWidgets.QTreeWidgetItem(parent, [label, identity])
            item.setData(0, QtCore.Qt.UserRole, node.path)
            for child in node.children:
                add_node(item, child)

        add_node(self.structure, model.root)
        self.model = model
        self.structure.expandAll()
        self.status.setText('Draft structure shown. Fabric syntax and capabilities have not been validated.')

    def refresh_runnables(self):
        self.runnable_pairs = ()
        self.runnable_combo.clear()
        self._update_apply_state()
        self.runnable_status.setText('Refreshing runnable specifications...')
        self.requests.request('runnable')

    def _runnable_ready(self, pairs):
        self.runnable_pairs = pairs
        self.runnable_combo.clear()
        for interface, provider in pairs:
            self.runnable_combo.addItem(f'{interface} / {provider}', (interface, provider))
        self.runnable_status.setText(f'{len(pairs)} runnable interface/provider pairs loaded; refresh to update.')
        self._update_apply_state()

    def _runnable_failed(self, error):
        self.runnable_pairs = ()
        self.runnable_combo.clear()
        self.runnable_status.setText(f'Runnable specifications unavailable: {error}')
        self._update_apply_state()

    def _runnable_busy_changed(self, busy):
        self.refresh_runnable_button.setEnabled(not busy)

    def _update_apply_state(self):
        if not hasattr(self, 'apply_runnable_button'):
            return
        selected = self.structure.currentItem() if hasattr(self, 'structure') else None
        self.apply_runnable_button.setEnabled(bool(
            self.model is not None and selected is not None and selected.text(0) == 'Runner' and
            self.runnable_combo.currentIndex() >= 0 and self.runnable_pairs))

    def apply_runnable(self):
        item = self.structure.currentItem()
        if self.model is None or item is None or not self.runnable_pairs:
            return
        pair = self.runnable_combo.currentData()
        if not pair or tuple(pair) not in self.runnable_pairs:
            return
        try:
            self.model.set_runner_pair(tuple(item.data(0, QtCore.Qt.UserRole)), pair[0], pair[1], self.runnable_pairs)
        except ValueError as exc:
            self.status.setText(f'Cannot edit runner: {exc}')
            return
        xml = self.model.to_xml()
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        cursor.insertText(xml)
        self.inspect_structure()

    def close_requests(self):
        self.requests.close()