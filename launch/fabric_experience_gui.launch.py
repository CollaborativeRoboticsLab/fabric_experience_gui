#!/usr/bin/env python3

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description() -> LaunchDescription:
    db_path_arg = DeclareLaunchArgument(
        'db_path',
        default_value='',
        description='Optional path to core_graphrag.sqlite3 opened at startup.',
    )
    audit_root_arg = DeclareLaunchArgument(
        'audit_root',
        default_value='',
        description='Optional path to planner_prompt_audit opened at startup.',
    )
    feedback_root_arg = DeclareLaunchArgument(
        'feedback_root',
        default_value='',
        description='Root containing generated_plans.json and optional user_feedback.json execution directories.',
    )
    out_dir_arg = DeclareLaunchArgument(
        'out_dir',
        default_value='offline_functional_outputs',
        description='Output directory for headless offline workflow artifacts.',
    )
    headless_arg = DeclareLaunchArgument(
        'headless',
        default_value='false',
        description='When true, run a non-GUI inspector automation entrypoint instead of the Qt window.',
    )
    headless_task_arg = DeclareLaunchArgument(
        'headless_task',
        default_value='offline_workflow',
        description='Headless task selector: offline_workflow or focused_checks.',
    )
    workspace_root_arg = DeclareLaunchArgument(
        'workspace_root',
        default_value='.',
        description='Workspace root for focused headless checks.',
    )
    analyze_terminal_success_arg = DeclareLaunchArgument(
        'analyze_terminal_success',
        default_value='false',
        description='When true in GUI mode, export terminal-success threshold analysis at startup from feedback and DB artifacts.',
    )
    terminal_success_out_dir_arg = DeclareLaunchArgument(
        'terminal_success_out_dir',
        default_value='terminal_success_analysis',
        description='Output directory for startup terminal-success analysis artifacts.',
    )
    planning_request_id_arg = DeclareLaunchArgument(
        'planning_request_id',
        default_value='',
        description='Optional planning request id for explanation verification in headless workflow mode.',
    )
    candidate_plan_id_arg = DeclareLaunchArgument(
        'candidate_plan_id',
        default_value='',
        description='Optional candidate plan id for explanation verification in headless workflow mode.',
    )
    graph_hash_arg = DeclareLaunchArgument(
        'graph_hash',
        default_value='',
        description='Optional graph hash for explanation verification in headless workflow mode.',
    )
    candidate_node_id_arg = DeclareLaunchArgument(
        'candidate_node_id',
        default_value='',
        description='Optional candidate node id for explanation verification in headless workflow mode.',
    )

    gui_process = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'fabric_experience_gui', 'inspector_gui.py',
            '--db-path', LaunchConfiguration('db_path'),
            '--audit-root', LaunchConfiguration('audit_root'),
            '--feedback-root', LaunchConfiguration('feedback_root'),
        ],
        output='screen',
        condition=UnlessCondition(LaunchConfiguration('headless')),
    )

    startup_terminal_success_process = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'fabric_experience_gui', 'run_terminal_success_analysis.py',
            '--feedback-root', LaunchConfiguration('feedback_root'),
            '--db-path', LaunchConfiguration('db_path'),
            '--out-dir', LaunchConfiguration('terminal_success_out_dir'),
        ],
        output='screen',
        condition=IfCondition(
            PythonExpression([
                "'", LaunchConfiguration('headless'), "' == 'false' and '",
                LaunchConfiguration('analyze_terminal_success'),
                "' == 'true' and '",
                LaunchConfiguration('feedback_root'),
                "' != '' and '",
                LaunchConfiguration('db_path'),
                "' != ''",
            ])
        ),
    )

    headless_workflow_process = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'fabric_experience_gui', 'run_offline_functional_workflow.py',
            '--db-path', LaunchConfiguration('db_path'),
            '--audit-root', LaunchConfiguration('audit_root'),
            '--feedback-root', LaunchConfiguration('feedback_root'),
            '--out-dir', LaunchConfiguration('out_dir'),
            '--planning-request-id', LaunchConfiguration('planning_request_id'),
            '--candidate-plan-id', LaunchConfiguration('candidate_plan_id'),
            '--graph-hash', LaunchConfiguration('graph_hash'),
            '--candidate-node-id', LaunchConfiguration('candidate_node_id'),
        ],
        output='screen',
        condition=IfCondition(
            PythonExpression([
                "'", LaunchConfiguration('headless'), "' == 'true' and '",
                LaunchConfiguration('headless_task'),
                "' == 'offline_workflow'",
            ])
        ),
    )

    headless_checks_process = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'fabric_experience_gui', 'run_focused_checks.py',
            '--workspace-root', LaunchConfiguration('workspace_root'),
        ],
        output='screen',
        condition=IfCondition(
            PythonExpression([
                "'", LaunchConfiguration('headless'), "' == 'true' and '",
                LaunchConfiguration('headless_task'),
                "' == 'focused_checks'",
            ])
        ),
    )

    return LaunchDescription([
        db_path_arg,
        audit_root_arg,
        feedback_root_arg,
        out_dir_arg,
        headless_arg,
        headless_task_arg,
        workspace_root_arg,
        analyze_terminal_success_arg,
        terminal_success_out_dir_arg,
        planning_request_id_arg,
        candidate_plan_id_arg,
        graph_hash_arg,
        candidate_node_id_arg,
        gui_process,
        startup_terminal_success_process,
        headless_workflow_process,
        headless_checks_process,
    ])