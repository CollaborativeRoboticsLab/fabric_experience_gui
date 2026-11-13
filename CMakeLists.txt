cmake_minimum_required(VERSION 3.8)
project(fabric_experience_gui)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(ament_cmake_pytest REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/inspector_gui.py
  scripts/rqt_experience_gui.py
  scripts/export_retrieval_prompt_audit.py
  scripts/summarize_planner_prompt_audit.py
  scripts/plot_core_graphrag_3d.py
  scripts/run_offline_functional_workflow.py
  scripts/run_focused_checks.py
  scripts/run_terminal_success_analysis.py
  DESTINATION lib/${PROJECT_NAME}
)

install(FILES plugin.xml
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)

  ament_add_pytest_test(test_sqlite_reader
    test/test_sqlite_reader.py
  )

  ament_add_pytest_test(test_qt_widget
    test/test_qt_widget.py
  )

  ament_add_pytest_test(test_score_client
    test/test_score_client.py
  )

  ament_add_pytest_test(test_automation
    test/test_automation.py
  )

  ament_add_pytest_test(test_plan_sandbox_helpers
    test/test_plan_sandbox_helpers.py
  )

  ament_add_pytest_test(test_fabric_graph
    test/test_fabric_graph.py
  )

  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()