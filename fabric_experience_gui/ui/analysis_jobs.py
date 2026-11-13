from __future__ import annotations

from pathlib import Path

from python_qt_binding import QtWidgets


class AnalysisJobsPanel(QtWidgets.QWidget):
    def __init__(self, inspector_widget):
        super().__init__()
        self.inspector_widget = inspector_widget

        self.retrieval_out_edit = QtWidgets.QLineEdit()
        self.summary_out_edit = QtWidgets.QLineEdit()
        self.feedback_root_edit = QtWidgets.QLineEdit()
        self.workflow_out_edit = QtWidgets.QLineEdit()
        self.calibration_out_edit = QtWidgets.QLineEdit()
        self.workspace_root_edit = QtWidgets.QLineEdit()
        self.plot_path_edit = QtWidgets.QLineEdit()
        self.proposal_path_edit = QtWidgets.QLineEdit()
        self.request_id_edit = QtWidgets.QLineEdit()
        self.plan_id_edit = QtWidgets.QLineEdit()
        self.graph_hash_edit = QtWidgets.QLineEdit()
        self.node_id_edit = QtWidgets.QLineEdit()
        self.high_prompt_spin = QtWidgets.QSpinBox()
        self.low_signal_spin = QtWidgets.QSpinBox()
        self.component_combo = QtWidgets.QComboBox()
        self.proposal_kind_combo = QtWidgets.QComboBox()
        self.proposal_summary_edit = QtWidgets.QLineEdit()
        self.proposal_notes_edit = QtWidgets.QPlainTextEdit()
        self.label_nodes_check = QtWidgets.QCheckBox('Label nodes in plot')
        self.drop_isolated_check = QtWidgets.QCheckBox('Drop isolated nodes in plot')

        self._build_layout()
        for edit, tip in (
            (self.request_id_edit, 'Optional planning request ID for explanation verification.'),
            (self.plan_id_edit, 'Optional candidate plan ID for explanation verification.'),
            (self.graph_hash_edit, 'Optional graph hash for explanation verification.'),
            (self.node_id_edit, 'Optional candidate node ID for explanation verification.'),
            (self.proposal_summary_edit, 'Short summary to include in the tuning proposal.'),
            (self.proposal_notes_edit, 'Review notes for the proposal; the database is not modified.'),
            (self.high_prompt_spin, 'Prompt length threshold used by the planner summary.'),
            (self.low_signal_spin, 'Low-signal item threshold used by the planner summary.'),
            (self.component_combo, 'Choose all graph components or only the largest for the plot.'),
            (self.proposal_kind_combo, 'Choose the type of non-destructive tuning proposal.'),
            (self.label_nodes_check, 'Include node labels in the 3D plot.'),
            (self.drop_isolated_check, 'Exclude isolated nodes from the 3D plot.'),
        ):
            edit.setToolTip(tip)
        button_tips = {
            'Use Current Defaults': 'Replace the analysis paths with defaults based on the current inputs.',
            'Run Retrieval Audit Export': 'Export retrieval statistics from the loaded GraphRAG database.',
            'Run Planner Summary Export': 'Summarize the loaded planner prompt audits.',
            'Run Offline Workflow': 'Run the offline analysis workflow using the specified inputs and output directory.',
            'Run Focused Checks': 'Build and test the focused package set in the specified workspace.',
            'Run Terminal Success Analysis': 'Analyze saved feedback and export threshold recommendations.',
            'Run 3D Plot Export': 'Export a 3D plot of the loaded GraphRAG graph.',
            'Write Tuning Proposal': 'Write a review proposal without changing the GraphRAG database.',
        }
        for button in self.findChildren(QtWidgets.QPushButton):
            if button.text() in button_tips:
                button.setToolTip(button_tips[button.text()])
        self.sync_defaults_from_widget()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        intro = QtWidgets.QLabel('Analysis Jobs')
        intro.setStyleSheet('font-weight: bold;')
        layout.addWidget(intro)

        layout.addWidget(QtWidgets.QLabel('Reusable export paths and parameters for repeated offline analysis runs.'))

        layout.addLayout(self._path_row('Retrieval Audit Dir', self.retrieval_out_edit, self._browse_retrieval_dir))
        layout.addLayout(self._path_row('Planner Summary Dir', self.summary_out_edit, self._browse_summary_dir))
        layout.addLayout(self._path_row('Feedback Root', self.feedback_root_edit, self._browse_feedback_root))
        layout.addLayout(self._path_row('Workflow Output Dir', self.workflow_out_edit, self._browse_workflow_dir))
        layout.addLayout(self._path_row('Calibration Dir', self.calibration_out_edit, self._browse_calibration_dir))
        layout.addLayout(self._path_row('Workspace Root', self.workspace_root_edit, self._browse_workspace_root))
        layout.addLayout(self._path_row('3D Plot Output', self.plot_path_edit, self._browse_plot_path))
        layout.addLayout(self._path_row('Proposal Output', self.proposal_path_edit, self._browse_proposal_path))

        explanation_row = QtWidgets.QHBoxLayout()
        explanation_row.addWidget(QtWidgets.QLabel('Request Id'))
        self.request_id_edit.setPlaceholderText('Optional for explanation verification')
        explanation_row.addWidget(self.request_id_edit, stretch=1)
        explanation_row.addWidget(QtWidgets.QLabel('Plan Id'))
        self.plan_id_edit.setPlaceholderText('candidate_plan_id')
        explanation_row.addWidget(self.plan_id_edit, stretch=1)
        layout.addLayout(explanation_row)

        explanation_row_2 = QtWidgets.QHBoxLayout()
        explanation_row_2.addWidget(QtWidgets.QLabel('Graph Hash'))
        self.graph_hash_edit.setPlaceholderText('graph_hash')
        explanation_row_2.addWidget(self.graph_hash_edit, stretch=1)
        explanation_row_2.addWidget(QtWidgets.QLabel('Node Id'))
        self.node_id_edit.setPlaceholderText('Optional candidate_node_id')
        explanation_row_2.addWidget(self.node_id_edit, stretch=1)
        layout.addLayout(explanation_row_2)

        prompt_row = QtWidgets.QHBoxLayout()
        prompt_row.addWidget(QtWidgets.QLabel('High Prompt Chars'))
        self.high_prompt_spin.setRange(1, 100000)
        self.high_prompt_spin.setValue(1200)
        prompt_row.addWidget(self.high_prompt_spin)
        prompt_row.addWidget(QtWidgets.QLabel('Low Signal Items'))
        self.low_signal_spin.setRange(0, 1000)
        self.low_signal_spin.setValue(2)
        prompt_row.addWidget(self.low_signal_spin)
        layout.addLayout(prompt_row)

        plot_row = QtWidgets.QHBoxLayout()
        plot_row.addWidget(QtWidgets.QLabel('Plot Component'))
        self.component_combo.addItems(['all', 'largest'])
        plot_row.addWidget(self.component_combo)
        layout.addLayout(plot_row)

        proposal_row = QtWidgets.QHBoxLayout()
        proposal_row.addWidget(QtWidgets.QLabel('Proposal Kind'))
        self.proposal_kind_combo.addItems(['community_regrouping', 'threshold_recalibration', 'general_review'])
        proposal_row.addWidget(self.proposal_kind_combo)
        layout.addLayout(proposal_row)

        self.proposal_summary_edit.setPlaceholderText('Short summary of the proposed tuning change')
        layout.addWidget(self.proposal_summary_edit)
        self.proposal_notes_edit.setPlaceholderText(
            'Capture review notes or suggested config changes here. This writes a proposal artifact and never mutates the database.'
        )
        self.proposal_notes_edit.setMaximumHeight(120)
        layout.addWidget(self.proposal_notes_edit)

        layout.addWidget(self.label_nodes_check)
        layout.addWidget(self.drop_isolated_check)
        self.label_nodes_check.setChecked(True)

        sync_button = QtWidgets.QPushButton('Use Current Defaults')
        sync_button.clicked.connect(self.sync_defaults_from_widget)
        layout.addWidget(sync_button)

        run_retrieval_button = QtWidgets.QPushButton('Run Retrieval Audit Export')
        run_retrieval_button.clicked.connect(self.run_retrieval_export)
        layout.addWidget(run_retrieval_button)

        run_summary_button = QtWidgets.QPushButton('Run Planner Summary Export')
        run_summary_button.clicked.connect(self.run_planner_summary)
        layout.addWidget(run_summary_button)

        run_workflow_button = QtWidgets.QPushButton('Run Offline Workflow')
        run_workflow_button.clicked.connect(self.run_offline_workflow)
        layout.addWidget(run_workflow_button)

        run_checks_button = QtWidgets.QPushButton('Run Focused Checks')
        run_checks_button.clicked.connect(self.run_focused_checks)
        layout.addWidget(run_checks_button)

        run_calibration_button = QtWidgets.QPushButton('Run Terminal Success Analysis')
        run_calibration_button.clicked.connect(self.run_terminal_success_analysis)
        layout.addWidget(run_calibration_button)

        run_plot_button = QtWidgets.QPushButton('Run 3D Plot Export')
        run_plot_button.clicked.connect(self.run_plot_export)
        layout.addWidget(run_plot_button)

        export_proposal_button = QtWidgets.QPushButton('Write Tuning Proposal')
        export_proposal_button.clicked.connect(self.run_tuning_proposal_export)
        layout.addWidget(export_proposal_button)

        layout.addStretch(1)

    def _path_row(self, label: str, line_edit: QtWidgets.QLineEdit, browse_callback) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(label))
        line_edit.setToolTip(f'Path for {label.lower()}.')
        row.addWidget(line_edit, stretch=1)
        browse_button = QtWidgets.QPushButton('Browse')
        browse_button.setToolTip(f'Select a path for {label.lower()}.')
        browse_button.clicked.connect(browse_callback)
        row.addWidget(browse_button)
        return row

    def sync_defaults_from_widget(self) -> None:
        self.retrieval_out_edit.setText(str(self.inspector_widget.default_retrieval_output_dir()))
        self.summary_out_edit.setText(str(self.inspector_widget.default_summary_output_dir()))
        self.feedback_root_edit.setText(self.inspector_widget.current_generated_root())
        self.workflow_out_edit.setText(str(self.inspector_widget.default_workflow_output_dir()))
        self.calibration_out_edit.setText(str(self.inspector_widget.default_terminal_success_analysis_dir()))
        self.workspace_root_edit.setText(str(Path.cwd()))
        self.plot_path_edit.setText(str(self.inspector_widget.default_plot_output_path()))
        self.proposal_path_edit.setText(str(self.inspector_widget.default_proposal_output_path()))

    def _browse_retrieval_dir(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select retrieval audit output directory', self.retrieval_out_edit.text().strip())
        if selected:
            self.retrieval_out_edit.setText(selected)

    def _browse_summary_dir(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select planner summary output directory', self.summary_out_edit.text().strip())
        if selected:
            self.summary_out_edit.setText(selected)

    def _browse_feedback_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select feedback root directory', self.feedback_root_edit.text().strip())
        if selected:
            self.feedback_root_edit.setText(selected)

    def _browse_workflow_dir(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select offline workflow output directory', self.workflow_out_edit.text().strip())
        if selected:
            self.workflow_out_edit.setText(selected)

    def _browse_calibration_dir(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select terminal-success analysis output directory', self.calibration_out_edit.text().strip())
        if selected:
            self.calibration_out_edit.setText(selected)

    def _browse_workspace_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select workspace root', self.workspace_root_edit.text().strip())
        if selected:
            self.workspace_root_edit.setText(selected)

    def _browse_plot_path(self) -> None:
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Select 3D graph plot output', self.plot_path_edit.text().strip(), 'PNG image (*.png);;All files (*.*)')
        if selected:
            self.plot_path_edit.setText(selected)

    def _browse_proposal_path(self) -> None:
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Select tuning proposal output', self.proposal_path_edit.text().strip(), 'JSON file (*.json);;All files (*.*)')
        if selected:
            self.proposal_path_edit.setText(selected)

    def run_retrieval_export(self) -> None:
        out_dir = Path(self.retrieval_out_edit.text().strip())
        report = self.inspector_widget.run_retrieval_export(out_dir)
        self.inspector_widget.status_label.setText(f"Retrieval audit exported to {out_dir} with {report['summary']['plan_count']} plans.")

    def run_planner_summary(self) -> None:
        out_dir = Path(self.summary_out_edit.text().strip())
        report = self.inspector_widget.run_planner_summary_export(out_dir, high_prompt_chars=self.high_prompt_spin.value(), low_signal_items=self.low_signal_spin.value())
        self.inspector_widget.status_label.setText(f"Planner prompt summary exported to {out_dir} with {report['summary']['request_count']} requests.")

    def run_offline_workflow(self) -> None:
        feedback_root = Path(self.feedback_root_edit.text().strip())
        out_dir = Path(self.workflow_out_edit.text().strip())
        report = self.inspector_widget.run_offline_workflow(
            feedback_root,
            out_dir,
            planning_request_id=self.request_id_edit.text().strip(),
            candidate_plan_id=self.plan_id_edit.text().strip(),
            graph_hash=self.graph_hash_edit.text().strip(),
            candidate_node_id=self.node_id_edit.text().strip(),
        )
        explanation = report.get('explanation_verification')
        suffix = ''
        if explanation is not None:
            suffix = f" explanation_success={explanation.get('success', False)}"
        self.inspector_widget.status_label.setText(
            f"Offline workflow exported to {out_dir} requests={report['prompt_decision_support']['summary']['request_count']}{suffix}."
        )

    def run_focused_checks(self) -> None:
        workspace_root = Path(self.workspace_root_edit.text().strip())
        report = self.inspector_widget.run_focused_checks(workspace_root)
        self.inspector_widget.status_label.setText(
            f"Focused checks passed in {workspace_root} with {report['test_count']} test targets."
        )

    def run_terminal_success_analysis(self) -> None:
        feedback_root = Path(self.feedback_root_edit.text().strip())
        out_dir = Path(self.calibration_out_edit.text().strip())
        report = self.inspector_widget.run_terminal_success_analysis(feedback_root, out_dir)
        self.inspector_widget.status_label.setText(
            f"Terminal-success analysis exported to {out_dir} samples={report['summary']['sample_count']} threshold={report['summary']['best_single_threshold']}."
        )

    def run_plot_export(self) -> None:
        output_path = Path(self.plot_path_edit.text().strip())
        written_path = self.inspector_widget.run_graph_plot_export(output_path, label_nodes=self.label_nodes_check.isChecked(), drop_isolated=self.drop_isolated_check.isChecked(), component=self.component_combo.currentText())
        self.inspector_widget.status_label.setText(f'3D graph plot exported to {written_path}.')

    def run_tuning_proposal_export(self) -> None:
        output_path = Path(self.proposal_path_edit.text().strip())
        written_path = self.inspector_widget.run_tuning_proposal_export(output_path, proposal_kind=self.proposal_kind_combo.currentText(), summary=self.proposal_summary_edit.text().strip(), notes=self.proposal_notes_edit.toPlainText().strip())
        self.inspector_widget.status_label.setText(f'Non-destructive tuning proposal exported to {written_path}.')
