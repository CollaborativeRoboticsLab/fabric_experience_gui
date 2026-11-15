# Fabric Inspector: Planned Work

## GPT Luna Handoff

**Functional status: incomplete.** The read-only Fabric graph and an isolated
XML draft editor are implemented, including runner pair and parameter editing.
The GUI invokes the synchronous, non-dispatching `/fabric/plan/validate`
service with the exact draft. The Fabric server build and focused runtime test
pass, but a live GUI-to-server validation smoke test remains to be run. Visual
node/edge editing, safe generation, and explicit submission are not implemented.
Existing runtime and integration coverage also has gaps; a successful build or
parser test does not close them.

Continue in this order, keeping changes scoped and tracking any newly discovered
contract limitations:

1. Expand the opt-in actual Fabric parser comparisons using real plans and
	unsupported or lossy XML. Preserve raw drafts when structured editing cannot
	safely represent them. See `test/test_plan_sandbox_helpers.py`,
	`test/fabric_parser_probe.cpp`, and the parser test instructions in `README.md`.
2. Inspect runnable-spec metadata and Fabric parameter conversion before adding
	parameter validation. Report missing, stale, or insufficient metadata rather
	than treating it as valid, and preserve draft attributes on provider changes.
3. Run the live GUI-to-server validation smoke test in `docs/testing.md`, then
	add focused integration coverage for service discovery, valid and invalid
	results, edits after validation, and absence of dispatch side effects.
4. Implement visual node/edge editing only for structures the parser can safely
	represent. Then implement explicit submission with review, confirmation, and
	no automatic retry after an ambiguous timeout.
5. Establish safe generator preview behavior before enabling generation, and
	complete the outstanding runtime, rqt, and cross-container integration tests.

Prefer existing published topics for available information. The approved
exception is `/capabilities/get_runnable_specs`: the pinned capabilities2
source does not expose a runnable-spec topic. Editing, inspection, refresh, and
validation must not dispatch or mutate a live plan. Generation stays disabled
until its side effects are understood. Do not modify the separate Fabric
repository as part of GUI work without agreement.

The latest recorded GUI suite passed 59 tests with the opt-in native parser
probe; its comparisons are representative, not exhaustive. The focused
`fabric_server` build and `test_fabric_runtime` also pass. The live validation
smoke test is documented in `docs/testing.md` but remains unverified. The GUI worktree
contains uncommitted parser-test and documentation changes plus existing
untracked `build/`, `install/`, and `log/` directories. Preserve those changes
and artifacts. A clean-container build and cross-container discovery remain
unverified; see `ToDo` for the open checklist.

## GUI Reorganization And Repository Split

- Verify the separate repository's devcontainer, pinned source dependencies, and workspace setup in a clean container before treating the setup as complete.
- Verify ROS 2 service discovery and calls between separate devcontainers on the same host. Host networking alone is not a guarantee: ROS domain, discovery configuration, middleware, multicast or configured peers, interfaces, and firewall must also be compatible. Test discovery and service recovery with real containers.
- Fabric contains Generative Graph, Live Graph Execution, and Graph Editor. Generative Graph takes a prompt, obtains and displays a plan, and only dispatches after explicit review and validation. Graph Editor creates and edits an isolated draft with drag-and-drop capabilities and the same dispatch safeguards. These features depend on confirming the generator and non-dispatching validation APIs; do not imply that placeholders are functional.
- Complete tooltip coverage and verify that Analysis Jobs and existing Experience inspection, export, and proposal workflows remain accessible. Keep the sandbox non-dispatching and retain live scoring.
- Verify tab structure, control visibility, tooltips, graph labels, existing workflows, standalone/rqt behavior, and no accidental dispatch. Track incomplete integrations explicitly.

## Implementation Progress
- `/fabric/plan/validate` accepts the exact XML draft through a synchronous request/response callback and returns whether validation completed, whether configured validators passed, and a message. It does not enqueue a plan or call execution/mutation endpoints. The editor invalidates validation results after edits. The controlled GUI test covers exact payload delivery and no mutation calls; the server build and focused runtime test pass. The live GUI-to-server test remains open, and broad parameter type/value validation remains out of scope.

- The package, Python module, launch file and rqt wrapper were renamed to `fabric_experience_gui` and built in an earlier workspace. The standalone window opened on a virtual display, and the renamed rqt plugin was discovered and started; interrupted rqt shutdown emitted X11 and class-loader warnings. Old install artifacts are not removed automatically. Live-service and full rqt interaction checks after the rename remain open.
- Fabric and Experience tabs now contain the requested grouped views, and Analysis Jobs is an optional Experience panel. Live graph nodes show full interface names with identity tooltips. Generative Graph has a prompt field and read-only review area, but generation remains disabled. Graph Editor contains an isolated XML draft workspace; visual editing and submission are unavailable.
- Decision Support filtering selects a visible request, clears selection when there are no matches, and retains the filter when reports reload. Review-navigation buttons describe their selected request or sample.
- Standalone Ctrl+C closes the window and allows active graph requests to finish cleanup. Subprocess tests cover idle shutdown and a controlled in-flight request, and the installed `ros2 run` command exited with code 0 after SIGINT. Real graph requests remain bounded by their client timeouts; immediate cancellation is not implemented.
- `/fabric/plan/generate` has an `auto_queue` goal field, but the Experience generation path promotes selection and records pending feedback state without consulting it. Non-dispatching preview and its side effects require runtime clarification and tests before connecting the GUI.
- The XML draft workspace supports local load, atomic save, and well-formedness/root checking without converting through the sandbox graph or calling ROS. Replacing a modified draft or closing the standalone window offers save, discard, or cancel; canceled and failed saves preserve the draft. The check is not parser or capability validation. Offscreen tests cover file and syntax failures, modified state, and standalone close; arbitrary XML round trips and visual editing remain open.
- A restricted draft model and tree cover nested Plan/Control/Runner structures and preserve runner parameter attributes when replacing a runner's interface/provider pair. Unknown structural elements, runner child content, namespaces on structural elements, and document type declarations are rejected by the structured view; raw XML remains editable. Unchanged drafts retain their original XML, while edits may normalize formatting. An opt-in test calls the pinned Fabric XML parser directly and compares connections and typed parameters across a nested draft round trip and targeted edits. It covers all four control types, repeated runners, escaped attributes, and rejected structural content; broader parser compatibility remains open. The opt-in `colcon test` passed, as did all 59 GUI tests with the probe enabled.
- Parser coverage now also compares a checked-in copy of `fabric_server/plans/default.xml` before and after a runner parameter edit. The pinned parser API is `fabric::Plan` plus `XMLParser::parse()`, and parsing injects a `FabricCompletionRunner` (seven parsed nodes for six source runners). The probe and focused tests pass with that contract. Building the opt-in probe requires the `fabric_parser_xml` dependency chain; other real plans and unsupported or lossy XML cases remain open.
- Runnable metadata and parameter handling are now mapped: `/capabilities/get_runnable_specs` returns raw provider YAML, while GUI pair discovery currently uses only interface/provider names. The response has no content revision or update time for staleness checks. Fabric `ParameterValidation` checks required runtime-input satisfaction; an explicit value counts by name/alias without type/value checking, and unknown extra attributes are not rejected. The XML parser independently infers scalar type from lexical text, so `1` and `1.0` differ and provider type metadata does not control conversion. Provider changes preserve draft attributes, but those attributes may be invalid for the new provider. Do not present pair discovery or parser acceptance as parameter validation.
- Runner parameter attributes can be added, edited, and removed in the isolated draft, with XML name/value checks, undo, and no-op preservation. All 58 GUI tests passed using the pinned Python helpers and message packages. These checks do not validate parameter types or requirements against provider metadata.
- Runnable pairs are fetched on demand from `/capabilities/get_runnable_specs` using bounded background ROS calls. The pinned capabilities2 source offers this service, not a runnable-spec topic. The GUI rejects inconsistent metadata, clears old pairs during refresh or failure, and supports selecting a discovered pair for a runner. A controlled ROS service test covers editing, undo, service loss and recovery without calls to mutation endpoints. All 56 GUI tests passed on rerun using the pinned Python helpers and message packages; a graph-view item-count test failed once and passed individually and on rerun. Discovery does not validate retained parameters or prove the pair remains available later.
- rqt's plugin handler removes widgets unconditionally after shutdown, even if a widget rejects close. Plugin shutdown requires an explicit save or discard of a modified draft, returning to the choice after a canceled or failed save. Plugin-level tests cover those paths without writing drafts to settings; full rqt-host removal remains unverified.
- The GUI is now a separate repository with a published remote, a devcontainer, and a pinned Fabric, capabilities2, and prompt-tools manifest. The bootstrap refuses dirty or mismatched dependency checkouts and duplicate GUI packages. A clean container build and cross-container service discovery remain unverified.
- Phase 1 remains in progress. Open runtime and inspector work is listed below.
- Phase 2 has a separate read-only Fabric Graph tab, Qt-independent graph model, bounded ROS clients, and background request coordinator. Refresh is manual; loading XML also requests a parse. The three graph levels, selection, filtering, zoom and pan are implemented.
- The snapshot does not report confirmed connections or running-capability dependencies. Its timestamp is the last state capture, not a live health check; terminal states can be cleared before a client observes them. Instance entries are derived from valid connection endpoints, not an independent inventory.
- The existing Graph Overview is the Experience knowledge graph, and the Plan Sandbox is not the requested Fabric graph or draft editor.
- Inspector regressions include graph-model and Qt tests. The integrated inspector widget refreshed a live TurtleBot snapshot and parsed the same plan offscreen through real services. Standalone and rqt windows were exercised on a virtual display; rqt refreshed a populated controlled snapshot. A real ROS service test checks inspector refresh, view changes, service loss and recovery without calls to controlled submission, cancellation, connection or trigger endpoints. The full runtime side-effect checks remain to be verified.

## Goal And Scope

Keep the Experience database inspection and non-destructive proposal workflows intact. Extend the inspector to visualize a loaded plan and a live active Fabric, then add a separate draft editor and explicit plan submission. The graph is not the Experience knowledge graph: its nodes represent capabilities or capability instances, and its directed event edges represent execution connections. Dependency edges are a separate relationship.

Database mutation is not part of this work. Existing proposal exports remain non-destructive; any direct Experience database augmentation requires a separately agreed write API, validation, and safety policy.

## Current State

- The Plan Sandbox loads XML and displays plan/control/runner structure; it is not an authoritative live capability graph.
- `/fabric/plan/parse` returns parsed Fabric connections for supplied XML. `/fabric/plan/get_status` returns lifecycle status; `/fabric/plan/get_snapshot` returns the cached intended graph for the current dequeued plan.
- capabilities2 exposes running capabilities and dependency information. Its current running-capability response does not populate instance IDs, so it cannot reliably assign dependencies to specific plan instances. The `dependent_capabilities` field is populated from the running model's dependencies; preserve the actual direction and verify it in tests.
- `/fabric/plan/validate` parses supplied XML, refreshes capability information with a bounded wait, and invokes configured validators synchronously. The Graph Editor's live smoke-test procedure is in `docs/testing.md`. The service reports `completed`, `valid`, and a message; it does not queue a plan or interact with bond, capability use, connection, or trigger endpoints. `/fabric/plan/parse` remains parser-only. `/fabric/plan/submit` queues before asynchronous validation and may proceed to execution; it is not a validation shortcut.

## Phase 1: Remaining Runtime Work

- Verify partial and shutdown transitions. The gated fixture now observes `CAPABILITY_CONNECTING`; runtime tests also check `on_start` and mux wiring at `VALIDATING`, the recovery `on_failure` edge from user-validated TurtleBot plan 3, and repeated instances plus directed `on_success` wiring across `RUNNING`, `COMPLETED`, `CANCELLED`, and a controlled `CAPABILITY_CONNECT_FAILED` cleanup. The XML parser does not construct `on_stop` edges, so a test-only parser adds an in-memory stop edge after XML parsing. A component test verifies distinct directed `STOPPED` and `SUCCEEDED` requests to a controlled connection service and preserves both edges in `RUNNING` and `COMPLETED` snapshots. This does not verify production XML support, an actual stop event, or confirmed capability connections. Manufactured snapshots alone do not establish runtime transition behavior.
- Test service disappearance and recovery, error paths, and bounded responsiveness during shutdown. A test-only parser pauses inside the runtime parsing call before delegating to the XML parser: repeated bounded reads retain the same incomplete empty `PARSING` snapshot even after the fixture mutates the unpublished plan, and processing resumes after release. This does not exercise a pause inside the XML parser itself. Repeated bounded reads with consistent graphs are also verified during `CAPABILITY_CONNECTING` and blocked completion/cancellation/connection-failure cleanup; parse-failure cleanup returns a consistent incomplete empty graph. During gated connection, repeated reads make no additional connection or trigger requests. A controlled Fabric component unload/reload verifies snapshot service disappearance and reconnection with the same client. During unload with parsing blocked, client requests have bounded timeouts and any responses are checked, but the service may remain advertised without responding; inspector clients must handle this. Releasing the parser allows shutdown without starting capability discovery or triggering the plan, and shutdown also completes while capability discovery is held by a service gate. Parsing and cleanup tests observe no trigger calls during the bounded read checks, but do not establish the absence of all dispatch or mutation. Exercise the inspector clients against the controlled runtime transitions.
- Preserve the single-current-plan contract: event links are intended, not confirmed; capture time is not a health check; terminal snapshots are not history. Surface dependencies only with verified direction and identity, otherwise use provider-level relationships with unknown instance ownership. Coordinate any contract change with inspector clients.
- Capability discovery honors `capability_client.service_wait_timeout_sec` and recovers with the same client after the service returns; a focused test verifies this. The default is `-1`, so discovery remains unbounded during normal operation unless a timeout is configured, although shutdown interrupts the wait.

**Acceptance:** Remaining failure and concurrent-transition cases are demonstrated with deterministic tests. Reads remain internally consistent and do not dispatch, mutate, or wait indefinitely on execution. Do not mark Phase 1 complete from conversion or store tests alone.

## Snapshot Test Guidelines

- During blocked parsing, connecting, and shutdown/failure scenarios, issue bounded snapshot requests and verify consistent plan ID, lifecycle, connection completeness, instances, and event direction. Test no unexpected dispatch or state changes, and confirm service reconnection after a controlled restart. Keep fixtures isolated and clean up processes and test data.
- Run focused message/server tests and the opt-in component matrix in a sourced workspace; rebuild dynamically loaded consumers after plugin ABI changes. Run inspector regressions and standalone/rqt integration when their clients exist. Report commands, actual results, skipped or blocked checks, and package-wide failures separately; avoid reformatting unrelated changes or claiming the existing formatter failures are all unrelated to this work.

## Phase 2: Read-Only Visualization

Add a dedicated Fabric Graph view alongside the existing database and sandbox tabs. Provide a loaded-plan source using the parser service and a live source using the snapshot service. Live refresh must not block the Qt event loop; show the source, last successful refresh, unavailable service, stale snapshot, and partial or empty graph states.

Provide three selectable levels:

1. **Main capabilities:** aggregate plan instances by capability interface and provider, preserving and labeling event connections between groups.
2. **All instances:** show each parsed capability instance independently, with directed event labels.
3. **Instances and dependencies:** retain instance/event edges and add provider-level dependencies. Do not assign dependencies to an instance unless the source proves that identity.

Give users node and edge details, selection, zoom/pan, filtering, and a legend distinguishing event, dependency, and uncertain relationships. Preserve self-loops and parallel events when aggregation combines nodes. Use stable identities and a graph model independent of Qt rendering so the editor can reuse it.

**Acceptance:** Focused model and Qt tests verify each level, graph direction, aggregation, duplicate instances, dependency ambiguity, refresh failures, and source switching. Existing database browsing and sandbox tests continue to pass.

## Phase 3: Draft Editor And Validation

Introduce an isolated draft model; editing it must never alter a live plan. Support discovery of available interfaces and providers, adding/removing capability instances, setting parameters, and creating/removing event edges. Provide load/save and a reviewable XML representation. Determine which graph structures can be represented by the Fabric parser and preserve supported XML semantics; reject or clearly mark unsupported structures instead of silently losing data. Do not claim arbitrary graphs round-trip until parser and serialization tests prove it.

Expand actual Fabric XML parser tests with original and structurally edited drafts beyond the current nested-controls fixture. Compare parsed identities, event connections, and parameter values, including real-world plans and unsupported or lossy structures. Local XML round trips alone do not prove parser equivalence. Keep these tests isolated from plan submission and execution.

Then inspect the runnable-spec metadata and Fabric's parameter conversion and validation behavior. Validate only names, values, types, and requirements supported by that contract, and distinguish missing, stale, or insufficient metadata from a valid result. Cover unknown parameters, missing required values, invalid values, provider changes, and metadata loss or recovery without silently discarding draft attributes.

Validate identity, required fields, parameters, event endpoints, and parser-supported structure locally. Use the existing parser and appropriate Fabric validation path to check the exact serialized draft; parsing alone is not full runtime validation. If no non-dispatching validation API exists, define and implement one or explicitly report the limitation before enabling dispatch. Invalidate validation when the draft changes.

**Acceptance:** Tests cover round trips, unsupported XML, invalid or missing providers and parameters, cyclic or otherwise unsupported structures, edit-after-validation, and the absence of side effects while editing or validating.

## Phase 4: Explicit Submission

Submit only a validated, unchanged draft after a user reviews the exact XML and confirms the action. Call `/fabric/plan/submit` and show the returned ID or rejection; monitor lifecycle separately using Fabric status. Make it clear that accepted means queued, not running or completed. Handle disconnection, server rejection, and timeout without automatically retrying an ambiguous request, since it may already have been accepted. Keep draft and live views separate.

**Acceptance:** Tests verify confirmation, exact payload, validation freshness, accepted/rejected responses, timeout handling, lifecycle updates, and prevention of accidental or duplicate submissions. No edit, refresh, validation, or view change triggers dispatch.

## Integration And Open Decisions

- Test the runtime snapshot and inspector clients in isolation, then exercise the complete flow with a controlled Fabric/capabilities2 setup. Cover standalone and rqt operation and regression-test existing inspector workflows.
- Document service names, ROS dependencies, configuration, graph semantics, identity limitations, refresh behavior, and submission risks. Build and test affected message, server, and inspector packages in a sourced workspace.
- The inspector uses manual refresh; switching sources or levels does not automatically request data. The existing snapshot service is `/fabric/plan/get_snapshot`; capabilities2's bounded event history cannot alone confirm current connection state. Revisit confirmation only if a reliable current-state source becomes available.
- Confirm whether capability aggregation by interface and provider matches the desired meaning of "main capabilities"; retain provider distinctions to avoid misleading merges.
- Determine the supported editor graph/XML subset and validation API before committing to arbitrary graph construction or dispatch.
