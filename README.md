# Fabric Experience GUI

`fabric_experience_gui` is the offline inspection package for persisted Experience artifacts. It is intended for development, evaluation, and calibration work when you want to inspect the GraphRAG database and prompt-audit outputs without launching the full Experience planning stack.

The package now uses Qt through `python_qt_binding`, which matches the ROS GUI ecosystem more closely than the initial Tkinter prototype and lets the same widget run as both a standalone tool and an `rqt` plugin.

## What It Provides

- A Qt GUI for browsing GraphRAG tables directly from `core_graphrag.sqlite3`
- Proxy-backed sortable tables with primary and secondary column filters
- A rendered Qt graph canvas with bidirectional node selection between the scene and inspector panels
- A read-only `Fabric > Live Graph Execution` view for parsed plans and live intended connections
- A `Plan Sandbox` tab for loading Fabric XML directly into the GUI as a structural graph
- A `Request Review` tab that joins prompt-audit iterations, persisted node explanations, and selected generated-plan snapshots per planning request
- A `Decision Support` tab that summarizes request-level detailed-vs-community recommendations from saved prompt audits and feedback artifacts
- A `Calibration Review` tab that surfaces offline terminal-success threshold candidates and proposal values from saved feedback artifacts
- Prompt-audit inspection for planner-generated JSON artifacts
- A retrieval-prompt audit exporter for `plan_node_score_explanation`
- A planner prompt-audit summarizer for generation and refinement iterations
- A full offline workflow runner for retrieval, prompt, reasoning, decision-support, and optional explanation verification artifacts
- A terminal-success analysis export that proposes offline RAPFS threshold candidates from saved feedback artifacts
- A 3D graph plotting utility for the persisted graph structure
- A focused build-and-check runner for the core Experience evaluation packages
- A non-destructive tuning proposal exporter for community or threshold review follow-up
- An `rqt` plugin wrapper around the same inspector widget

## Build

The GUI is an independent repository. To use its ROS Jazzy devcontainer, clone it
and open the repository folder in VS Code using **Reopen in Container**:

```bash
git clone https://github.com/CollaborativeRoboticsLab/fabric_experience_gui.git
cd fabric_experience_gui
```

The devcontainer's post-create command imports the pinned Fabric, capabilities2,
and prompt-tools repositories from `dependencies.repos`, installs the discovered
ROS dependencies, and builds the GUI in `~/fabric_gui_ws`. It requires network
access. It refuses to modify dependency checkouts that are dirty or at another
revision. Set `FABRIC_GUI_WS` before running the bootstrap manually to use a
different workspace:

```bash
bash .devcontainer/setup-workspace.sh
source /opt/ros/jazzy/setup.bash
source ~/fabric_gui_ws/install/setup.bash
ros2 run fabric_experience_gui inspector_gui.py
```

If `FABRIC_GUI_WS` is set, source that workspace's `install/setup.bash` instead.
The container uses the host X11 socket and `DISPLAY`; desktop access also depends
on the host's X11 authorization. The devcontainer setup has not yet been verified
in a clean container.

For an existing colcon workspace with the dependencies already present:

```bash
colcon build --packages-up-to fabric_experience_gui
source install/setup.bash
```

This is a package and Python module rename: commands and imports using
`fabric_experience_inspector` need updating. An older install may still advertise
the previous package or rqt plugin until its generated artifacts are cleaned.

## GUI Usage

From the colcon workspace root, start the standalone inspector:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run fabric_experience_gui inspector_gui.py
```

Launch the GUI with optional database, prompt-audit, and feedback artifact paths:

```bash
ros2 run fabric_experience_gui inspector_gui.py \
  --db-path /path/to/core_graphrag.sqlite3 \
  --audit-root /path/to/planner_prompt_audit \
  --feedback-root /path/to/feedback_root
```

Or use the package launch file:

```bash
ros2 launch fabric_experience_gui fabric_experience_gui.launch.py db_path:=/path/to/core_graphrag.sqlite3
```

Enable startup-time terminal-success analysis from the same saved feedback artifacts when you want the launch flow to emit a fresh threshold-analysis export automatically:

```bash
ros2 launch fabric_experience_gui fabric_experience_gui.launch.py \
  db_path:=/path/to/core_graphrag.sqlite3 \
  feedback_root:=/path/to/feedback_root \
  analyze_terminal_success:=true \
  terminal_success_out_dir:=/tmp/terminal_success_analysis
```

Run the same package in headless offline-workflow mode:

```bash
ros2 launch fabric_experience_gui fabric_experience_gui.launch.py \
  headless:=true \
  headless_task:=offline_workflow \
  db_path:=/path/to/core_graphrag.sqlite3 \
  audit_root:=/path/to/planner_prompt_audit \
  feedback_root:=/path/to/feedback_root
```

Or run the focused build-and-check path headlessly:

```bash
ros2 launch fabric_experience_gui fabric_experience_gui.launch.py \
  headless:=true \
  headless_task:=focused_checks \
  workspace_root:=/home/ubuntu/colcon_ws
```

Or load the same widget in `rqt`:

```bash
rqt --standalone fabric_experience_gui/ExperienceInspectorPlugin
```

Or use the convenience wrapper:

```bash
ros2 run fabric_experience_gui rqt_experience_gui.py --db-path /path/to/core_graphrag.sqlite3 --audit-root /path/to/planner_prompt_audit
```

Inside the GUI you can:

- Use per-tab filters to narrow large tables without editing SQL queries
- Use primary and secondary column filters per tab to narrow large tables without editing SQL queries
- Sort tables by clicking column headers after a database loads
- Inspect the `Graph Overview` tab for high-level graph counts, node search, a rendered graph canvas, and bidirectional node selection
- Paste or load a Fabric XML plan into the `Plan Sandbox` tab and inspect its parsed structure as a graph
- Browse `Nodes`, `Edges`, `Communities`, `Plan Feedback`, `Node Explanations`, and `Scoring Epochs`
- Load a planner prompt-audit directory into the `Prompt Audits` tab
- Optionally load a generated-plan artifact directory so the `Request Review` tab can show the selected plan snapshot and reasoning alongside prompt iterations and persisted explanations
- Reuse that same generated-plan artifact root to populate the `Decision Support` tab with request-level recommendation rows and selected-plan outcomes
- Reuse that same generated-plan artifact root to populate the `Calibration Review` tab with threshold candidates, observed outcomes, and proposal values
- Launch retrieval-audit export, prompt-audit summary export, and 3D graph plot export directly from the toolbar
- Write non-destructive review proposals from the Experience toolbar or Analysis Jobs panel
- Reuse preset export paths and parameters from the optional `Analysis Jobs` panel for repeated offline runs
- Run the full offline workflow and focused package checks from the `Analysis Jobs` panel
- Run terminal-success threshold analysis from the `Analysis Jobs` panel
- Inspect the selected row in the detail pane without querying the database manually

The GUI reads the SQLite database directly. Offline inspection uses the Fabric-owned
Python helpers from `fabric_server` and does not require the Fabric server to be running.
The Live Graph Execution tab requires the relevant ROS services for parsing or live snapshots.

Optional plugin arguments can also be passed through `rqt`:

```bash
rqt --standalone fabric_experience_gui/ExperienceInspectorPlugin --args --db-path /path/to/core_graphrag.sqlite3 --audit-root /path/to/planner_prompt_audit
```

The standalone launch file also accepts both startup paths:

```bash
ros2 launch fabric_experience_gui fabric_experience_gui.launch.py \
  db_path:=/path/to/core_graphrag.sqlite3 \
  audit_root:=/path/to/planner_prompt_audit
```

Select `Experience > Analysis Jobs` to open the optional panel with reusable output paths and export parameters for retrieval audits, planner summaries, 3D plots, and non-destructive tuning proposals. The panel is hidden from Fabric views, including in rqt.

That same panel now also runs the full offline workflow and the focused build/test check set without leaving the GUI.

The toolbar also accepts an optional generated-plan artifact directory. Point it at a directory containing one or more `generated_plans.json` files and load it when you want the `Request Review` tab to merge selected candidate-plan snapshots into the same offline review surface.

## Non-Destructive Tuning Proposals

The inspector remains read-only with respect to `core_graphrag.sqlite3`. When offline review suggests community regrouping, threshold recalibration, or another tuning follow-up, use `Write Proposal` in the Experience toolbar or `Write Tuning Proposal` in the `Analysis Jobs` panel.

This writes a versioned JSON artifact containing:

- the current DB and audit-root inputs,
- the currently selected graph or plan node when available,
- graph and prompt-audit snapshot counts,
- optional review summary and notes,
- and an explicit `mutates_database: false` policy marker.

That keeps review and calibration work non-destructive by default while still producing a durable artifact that can be reviewed and converted into explicit config or export updates later.

## Live Graph Execution

Select `Live snapshot` and refresh to request `/fabric/plan/get_snapshot`, or load an
XML file to parse it using `/fabric/plan/parse`. Refresh is manual; changing sources
or graph levels does not request new data. Requests run outside the Qt event loop and
report unavailable services, stale captures, partial captures, and empty graphs.

The main-capabilities level aggregates by interface and provider; the other levels
show instances and directed event connections. The dependencies level optionally
requests `/capabilities/get_running_capabilities` on refresh. Dependencies are
provider-level, with instance ownership unknown; an unavailable response is not an
empty dependency list. It is sampled separately from the snapshot, not atomically.

The live graph is the cached intended graph for the current dequeued plan, not proof
that connections are active. Its timestamp is the last state capture, not a health
check; terminal states can disappear before refresh. Instances are derived from valid
connection endpoints, not an independent inventory. Viewing or refreshing does not
submit a plan.

Generative Graph provides a prompt field and read-only plan area, but generation is
disabled until safe preview is verified. The Graph Editor tab currently offers an
isolated XML draft with load, atomic save, and a well-formedness check. Inspect Structure
shows supported `Plan`, `Control`, and `Runner` elements in a tree. Controls must use
`sequential`, `parallel_any`, `parallel_all`, or `recovery`; each Plan or Control must
contain an executable element. Runners require interface and provider attributes and
may carry parameter attributes. Runner child elements or text, unknown structural
elements, namespaces on structural elements, and document type declarations are not
supported by the structured view; the XML editor can still load and save them.

Refresh Runnables requests `/capabilities/get_runnable_specs`, the available
capabilities2 service for runnable metadata. Select a runner and a returned pair to
replace its interface and provider in the draft. Existing parameter attributes are
preserved but may not be valid for the new provider. The list is a snapshot and must
be refreshed to reflect changes; failure clears it. An unchanged structured draft
retains its original XML, while editing may normalize its formatting. This is not
Fabric validation: parameters, parser behavior, and runtime availability remain
unchecked. Visual graph editing and dispatch are not available. The Plan Sandbox
remains non-dispatching.

Loading or replacing a modified draft, or closing the standalone window, offers
Save, Discard, or Cancel. A canceled or failed save keeps the draft open. When rqt
removes the plugin, it cannot cancel removal; the GUI
requires an explicit save or discard, and asks again after a canceled or failed save.
This behavior has plugin-level tests but has not been verified in a full rqt host.

## Separate Containers

The GUI can run in a separate repository and devcontainer when its ROS interfaces,
`fabric_server` Python helpers, Qt dependencies, and workspace build dependencies are
available there. The included devcontainer uses host networking and host IPC; these
share the host network and IPC namespaces and should be used only in a trusted setup.
Both sides must also use compatible ROS domain IDs, middleware and discovery
configuration, network interfaces, multicast or configured peers, and firewall rules.
Test service calls and recovery on the target containers; host networking alone does
not guarantee discovery. Cross-container service discovery is not yet verified.

## Plan Sandbox

The `Plan Sandbox` tab is for direct Fabric XML inspection inside the GUI.

You can:

- Paste Fabric XML directly into the editor or load it from an `.xml` file
- Parse the XML into a structural graph containing `Plan`, `Control`, and `Runner` nodes
- Inspect control-structure edges such as sequential success transitions, parallel branches, and recovery links
- Optionally paste or load a score JSON payload to overlay plan-level and node-level scoring fields when you already have them
- Call the live `/fabric/experience/score` service directly from the tab when the Fabric server is running

Important limitation:

- The sandbox parses plan structure locally, but it does not run the full RAPFS scoring stack by itself.
- Real score components still come from the integrated Fabric Experience scoring path, such as the live `/fabric/experience/score` service or exported score artifacts.
- When no score JSON is provided, the sandbox intentionally shows only structural information.

### Live Scoring From The Sandbox

When the Fabric server is running and the workspace has been sourced, the `Score via Service` action can call the live `/fabric/experience/score` service.

Provide:

- a task description,
- the Fabric XML plan,
- and optionally `planning_request_id`, `candidate_plan_id`, or `candidate_node_id`.

The returned score response is loaded back into the score-overlay editor automatically and applied to the parsed sandbox graph.

Live scoring uses `fabric_msgs/srv/ScorePlan` at `/fabric/experience/score`.
If the score service, `rclpy`, or `fabric_msgs` is unavailable, the inspector keeps the offline sandbox state intact and reports the failure without overwriting the current overlay.

## Retrieval Prompt Audit Export

Export detailed-vs-community retrieval context statistics from `plan_node_score_explanation`:

```bash
ros2 run fabric_experience_gui export_retrieval_prompt_audit.py /path/to/core_graphrag.sqlite3
```

Optional output directory:

```bash
ros2 run fabric_experience_gui export_retrieval_prompt_audit.py /path/to/core_graphrag.sqlite3 --out-dir retrieval_prompt_audit
```

This writes:

- `retrieval_prompt_audit.json`
- `node_prompt_audit.csv`
- `plan_prompt_audit.csv`

## Planner Prompt-Audit Summary

Summarize planner prompt-audit JSON files written by `experience_planner`:

```bash
ros2 run fabric_experience_gui summarize_planner_prompt_audit.py /path/to/planner_prompt_audit
```

Optional controls:

```bash
ros2 run fabric_experience_gui summarize_planner_prompt_audit.py \
  /path/to/planner_prompt_audit \
  --out-dir planner_prompt_audit_exports \
  --high-prompt-chars 1200 \
  --low-signal-items 2
```

This writes:

- `planner_prompt_audit_summary.json`
- `iteration_prompt_audit.csv`
- `request_prompt_audit.csv`
- `high_prompt_low_signal_requests.csv`

The summary includes a `community_mode_viability` assessment to help judge whether community-only semantic retrieval is strong enough to justify reduced prompt context.

## Offline Workflow

Run the full offline workflow directly when you want retrieval, prompt, reasoning, decision-support, and optional explanation-verification artifacts in one pass:

```bash
ros2 run fabric_experience_gui run_offline_functional_workflow.py \
  --db-path /path/to/core_graphrag.sqlite3 \
  --audit-root /path/to/planner_prompt_audit \
  --feedback-root /path/to/feedback_root \
  --out-dir /tmp/offline_functional_outputs
```

Optional explanation verification:

```bash
ros2 run fabric_experience_gui run_offline_functional_workflow.py \
  --db-path /path/to/core_graphrag.sqlite3 \
  --audit-root /path/to/planner_prompt_audit \
  --feedback-root /path/to/feedback_root \
  --out-dir /tmp/offline_functional_outputs \
  --planning-request-id pr_20260927_001 \
  --candidate-plan-id cp_001 \
  --graph-hash graph_001 \
  --candidate-node-id runner_1
```

## Focused Checks

Run the focused build-and-check set without the deleted shell wrapper:

```bash
ros2 run fabric_experience_gui run_focused_checks.py --workspace-root /home/ubuntu/colcon_ws
```

## Terminal-Success Analysis

Run the offline threshold-analysis export directly when you want candidate RAPFS cut points from saved plan outcomes:

```bash
ros2 run fabric_server export_terminal_success_analysis.py \
  /path/to/feedback_root \
  --db /path/to/core_graphrag.sqlite3 \
  --out-dir /tmp/terminal_success_analysis
```

The offline workflow now also writes `terminal_success_analysis/terminal_success_analysis.json` with threshold candidates and a non-destructive proposal section derived from observed feedback versus `final_rapfs`.

## 3D Graph Plotting

Render the persisted graph as a 3D plot:

```bash
ros2 run fabric_experience_gui plot_core_graphrag_3d.py /path/to/core_graphrag.sqlite3
```

Useful options:

```bash
ros2 run fabric_experience_gui plot_core_graphrag_3d.py \
  /path/to/core_graphrag.sqlite3 \
  --component largest \
  --label-nodes \
  --runtime-overlay auto \
  --output /tmp/core_graphrag_3d.png
```

The plotter will try to use runtime evidence from `skill_run_statistics` when available.

`numpy` and `matplotlib` are required for the 3D plotter. The Qt GUI and CSV/JSON exporters do not depend on them.

## Typical Offline Workflow

1. Open the Qt GUI on a saved `core_graphrag.sqlite3` to inspect nodes, edges, communities, explanations, scoring epochs, and the graph overview.
2. Load the matching `planner_prompt_audit` directory to inspect prompt iterations per request.
3. Optionally load a generated-plan artifact directory when you want to inspect the selected plan XML and reasoning for the same planning request.
4. Use the `Request Review` tab to inspect prompt iterations, persisted node explanations, and the selected generated-plan snapshot for one request in a single surface.
5. Use the `Decision Support` tab when you want a sortable request-level summary of whether detailed or community prompt context looks more appropriate on saved runs.
6. Use the built-in primary and secondary filters, sorting, and graph node filter to narrow the inspection surface quickly.
7. Click a node either in the graph canvas or the node list to synchronize the selection and inspect its neighbors.
8. Paste or load a Fabric XML plan into the `Plan Sandbox` tab and optionally overlay a score JSON payload when you want plan-specific inspection in the same tool.
9. Open the `Analysis Jobs` panel in Experience when you want stable output paths and parameters across repeated offline runs.
10. Run `export_retrieval_prompt_audit.py` to measure detailed-vs-community retrieval compression from persisted explanation rows when you want the same export from the command line.
11. Run `summarize_planner_prompt_audit.py` to aggregate prompt behavior across requests and check the `community_mode_viability` verdict.
12. Run `plot_core_graphrag_3d.py` when you need a visual view of connected graph structure and runtime overlays outside the GUI.
13. Open the same inspector inside `rqt` when you want it to live alongside other ROS Qt tools.

## Validation

Focused package validation currently uses:

```bash
colcon build --packages-select fabric_experience_gui
ctest --output-on-failure --test-dir build/fabric_experience_gui -R test_sqlite_reader
```