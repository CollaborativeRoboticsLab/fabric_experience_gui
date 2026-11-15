from python_qt_binding import QtCore, QtWidgets


class GenerativeGraphWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel('Task prompt'))
        self.generation_prompt = QtWidgets.QPlainTextEdit()
        self.generation_prompt.setPlaceholderText('Describe the task for the generated plan.')
        self.generation_prompt.setToolTip('Task description to use when plan generation becomes available.')
        self.generation_prompt.setMaximumHeight(160)
        layout.addWidget(self.generation_prompt)
        self.generate_button = QtWidgets.QPushButton('Generate plan')
        self.generate_button.setEnabled(False)
        self.generate_button.setToolTip('Unavailable until non-dispatching generation is verified.')
        layout.addWidget(self.generate_button, alignment=QtCore.Qt.AlignLeft)
        status = QtWidgets.QLabel('Plan generation and dispatch are unavailable pending safe preview and validation.')
        status.setWordWrap(True)
        layout.addWidget(status)
        layout.addWidget(QtWidgets.QLabel('Generated plan'))
        self.generated_plan_preview = QtWidgets.QPlainTextEdit()
        self.generated_plan_preview.setReadOnly(True)
        self.generated_plan_preview.setPlaceholderText('No generated plan available.')
        self.generated_plan_preview.setToolTip('Generated plan XML will appear here when safe preview is available.')
        layout.addWidget(self.generated_plan_preview, stretch=1)