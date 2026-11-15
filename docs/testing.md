# Live Plan Validation Smoke Test

This checks the Graph Editor against a running Fabric validation service. It
does not verify cross-container discovery or replace automated side-effect tests.
Use an isolated test system with no production robot or active Fabric instance.

## Build And Source

From the colcon workspace root:

```bash
cd /home/ubuntu/colcon_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to fabric_experience_gui fabric_server
source install/setup.bash
```

Open three terminals and source the same environment in each:

```bash
cd /home/ubuntu/colcon_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

## Start Fabric

Fabric queues a starter plan at startup. Override its packaged default plan
with the empty sequential fixture used by the component tests to avoid running
the example plan. The parser may still insert a completion runner, so startup is
not itself a no-dispatch test. In terminal 1:

```bash
printf '%s\n' '<Plan><Control type="sequential"/></Plan>' > /tmp/fabric-validation-bootstrap.xml
ros2 launch fabric_server fabric.launch.py \
  plan_file_path:=/tmp/fabric-validation-bootstrap.xml \
  start_prompt_tools:=false
```

The launch starts capabilities2 and its launch proxy. The validation service
needs the capabilities2 runnable-spec service. Leave this terminal running and
do not start another Fabric server in the same ROS domain.

## Check The Service

In terminal 2:

```bash
ros2 service type /fabric/plan/validate
ros2 service call /fabric/plan/validate fabric_msgs/srv/ValidatePlan "{plan: '<Plan>'}"
```

The type should be `fabric_msgs/srv/ValidatePlan`. The malformed XML response
should have `completed: true`, `valid: false`, and a parse-error message. If the
service is missing, check server startup and ROS domain/discovery settings.

## Validate From The GUI

In terminal 3:

```bash
ros2 run fabric_experience_gui inspector_gui.py
```

In Graph Editor:

1. Load a plan known to match the capabilities configured in this environment.
2. Click **Validate Draft**. A valid plan should report that configured
   validators passed. An incomplete result indicates a discovery or service
   problem, not a plan rejection.
3. Replace the draft with malformed XML such as `<Plan>` and validate again.
   The GUI should show a failure with a parser message.
4. Validate the known-good draft again, then edit it. The previous validation
   result must no longer be current; validate again for the changed text.

The validation request uses the exact editor text and does not submit the draft.
Do not use `/fabric/plan/submit` as a validation shortcut. Observe the server
and controlled capability endpoints to investigate unexpected activity; this
manual check alone does not prove absence of all side effects.

Close the GUI and stop the launch with Ctrl+C. Repeat discovery checks separately
for a GUI and server running in different containers.