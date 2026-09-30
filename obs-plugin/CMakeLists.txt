cmake_minimum_required(VERSION 3.16)
project(what_overlay_plugin LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(WHAT_OVERLAY_DEBUG "Enable debug logging for what_overlay plugin" OFF)
option(WHAT_OVERLAY_ENABLE_FRONTEND_PANEL "Enable OBS frontend tools-menu panel scaffold" ON)
option(WHAT_OVERLAY_ENABLE_QT_DOCK "Enable Qt custom dock implementation for frontend panel" ON)
option(WHAT_OVERLAY_BUILD_UNIT_TESTS "Build standalone unit tests for pure helper modules" ON)

# NOTE: This is a skeleton. On macOS, you can point at the OBS.app frameworks.
# Example paths (default OBS install):
#   OBS_INCLUDE_DIR = /Applications/OBS.app/Contents/Frameworks/libobs.framework/Headers
#   OBS_LIB_DIR     = /Applications/OBS.app/Contents/Frameworks

if(APPLE)
  if(NOT OBS_INCLUDE_DIR)
    set(OBS_INCLUDE_DIR "$ENV{HOME}/projects/obs-studio/libobs" CACHE PATH "OBS include dir")
  endif()
  if(NOT OBS_LIB_DIR)
    set(OBS_LIB_DIR "/Applications/OBS.app/Contents/Frameworks" CACHE PATH "OBS framework dir")
  endif()
  if(NOT OBS_CONFIG_DIR)
    set(OBS_CONFIG_DIR "$ENV{HOME}/projects/obs-studio/build/config" CACHE PATH "OBS config include dir")
  endif()
  if(NOT OBS_FRONTEND_API_INCLUDE_DIR)
    set(OBS_FRONTEND_API_INCLUDE_DIR "$ENV{HOME}/projects/obs-studio/frontend/api" CACHE PATH "OBS frontend API include dir")
  endif()
  if(NOT EXISTS "${OBS_CONFIG_DIR}/obsconfig.h")
    set(OBS_CONFIG_DIR "${CMAKE_CURRENT_LIST_DIR}/obsconfig" CACHE PATH "OBS config include dir" FORCE)
  endif()
  if(NOT OBS_DEPS_INCLUDE)
    file(GLOB _obs_deps_candidates "$ENV{HOME}/projects/obs-studio/.deps/obs-deps-*/include")
    list(LENGTH _obs_deps_candidates _obs_deps_len)
    if(_obs_deps_len GREATER 0)
      list(GET _obs_deps_candidates 0 OBS_DEPS_INCLUDE)
    endif()
  endif()
  if(NOT OBS_QT_FRAMEWORKS_DIR)
    file(GLOB _obs_qt_candidates "$ENV{HOME}/projects/obs-studio/.deps/obs-deps-qt6-*/lib")
    list(LENGTH _obs_qt_candidates _obs_qt_len)
    if(_obs_qt_len GREATER 0)
      list(GET _obs_qt_candidates 0 OBS_QT_FRAMEWORKS_DIR)
    endif()
    set(OBS_QT_FRAMEWORKS_DIR "${OBS_QT_FRAMEWORKS_DIR}" CACHE PATH "Qt frameworks dir for OBS plugin build")
  endif()
endif()

if(UNIX AND NOT APPLE)
  if(NOT OBS_INCLUDE_DIR)
    foreach(_obs_include_candidate
      /usr/include/obs
      /usr/local/include/obs
    )
      if(EXISTS "${_obs_include_candidate}/obs-module.h")
        set(OBS_INCLUDE_DIR "${_obs_include_candidate}" CACHE PATH "OBS include dir" FORCE)
        break()
      endif()
    endforeach()
  endif()
  if(NOT OBS_LIB_DIR)
    foreach(_obs_lib_candidate
      /usr/lib/x86_64-linux-gnu
      /usr/lib64
      /usr/lib
      /usr/local/lib64
      /usr/local/lib
    )
      if(EXISTS "${_obs_lib_candidate}/libobs.so")
        set(OBS_LIB_DIR "${_obs_lib_candidate}" CACHE PATH "OBS library dir" FORCE)
        break()
      endif()
    endforeach()
  endif()
endif()

set(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED OFF)
if(WHAT_OVERLAY_ENABLE_FRONTEND_PANEL)
  if(EXISTS "${OBS_FRONTEND_API_INCLUDE_DIR}/obs-frontend-api.h")
    set(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED ON)
  else()
    message(WARNING "WHAT_OVERLAY_ENABLE_FRONTEND_PANEL=ON but obs-frontend-api.h not found at OBS_FRONTEND_API_INCLUDE_DIR='${OBS_FRONTEND_API_INCLUDE_DIR}'. Frontend panel scaffold disabled.")
  endif()
endif()

set(WHAT_OVERLAY_QT_DOCK_ENABLED OFF)
if(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED AND WHAT_OVERLAY_ENABLE_QT_DOCK)
  if(APPLE)
    set(_qtwidgets_headers "${OBS_QT_FRAMEWORKS_DIR}/QtWidgets.framework/Versions/A/Headers")
    set(_qtgui_headers "${OBS_QT_FRAMEWORKS_DIR}/QtGui.framework/Versions/A/Headers")
    set(_qtcore_headers "${OBS_QT_FRAMEWORKS_DIR}/QtCore.framework/Versions/A/Headers")
    set(_qtnetwork_headers "${OBS_QT_FRAMEWORKS_DIR}/QtNetwork.framework/Versions/A/Headers")
    if(EXISTS "${_qtwidgets_headers}" AND EXISTS "${_qtgui_headers}" AND EXISTS "${_qtcore_headers}" AND EXISTS "${_qtnetwork_headers}")
      set(WHAT_OVERLAY_QT_DOCK_ENABLED ON)
    else()
      message(WARNING "Frontend panel enabled but Qt framework headers were not found under OBS_QT_FRAMEWORKS_DIR='${OBS_QT_FRAMEWORKS_DIR}'. Dock UI disabled.")
    endif()
  else()
    # Linux/other: Qt6 comes from the distro with a normal CMake package config, so use
    # find_package rather than hunting framework header directories. OBS on Linux is a
    # Qt6 application, so matching it here is what keeps the dock loadable in-process.
    find_package(Qt6 QUIET COMPONENTS Widgets Gui Core Network)
    if(Qt6_FOUND)
      # No AUTOMOC on purpose: the panel declares no Q_OBJECT and uses no signals/slots
      # keywords (connects go through function pointers), so it needs no moc pass -- and
      # macOS builds it the same way. Keep the two platforms symmetric.
      set(WHAT_OVERLAY_QT_DOCK_ENABLED ON)
    else()
      message(WARNING "Frontend panel enabled but Qt6 (Widgets/Gui/Core/Network) was not found. "
                      "Dock UI disabled -- install the Qt6 development packages "
                      "(e.g. qt6-base-dev on Debian/Ubuntu).")
    endif()
  endif()
endif()

add_library(what_overlay_plugin MODULE
  src/plugin.cpp
  src/browser_source.cpp
  src/overlay_source.cpp
  src/overlay_client.cpp
  src/overlay_config.cpp
  src/overlay_state.cpp
  src/render/color_font_utils.cpp
  src/layout/text_wrap_utils.cpp
  src/layout/font_metrics.cpp
  src/layout/fit_decider.cpp
  src/layout/caption_freezer.cpp
  src/layout/line_layout.cpp
  src/layout/visible_window_policy.cpp
  src/layout/overlay_label_policy.cpp
  src/layout/header_render_policy.cpp
  src/layout/body_render_pipeline.cpp
  src/layout/source_render_policy.cpp
  src/pipeline/payload_ingest_policy.cpp
  src/pipeline/header_activation_policy.cpp
  src/pipeline/header_source_sync_policy.cpp
  src/pipeline/transition_policy.cpp
  src/pipeline/render_geometry_policy.cpp
  src/pipeline/body_source_update_policy.cpp
  src/pipeline/body_fit_policy.cpp
  src/pipeline/body_text_fit_inputs.cpp
  src/pipeline/control_http_client.cpp
  src/pipeline/legacy_wrap_policy.cpp
  src/pipeline/payload_json_parser.cpp
  src/pipeline/runtime_adapter.cpp
  src/net_compat.cpp
)

if(WIN32)
  target_link_libraries(what_overlay_plugin ws2_32)
endif()

if(UNIX AND NOT APPLE)
  # Flatpak OBS ships libobs under /app/lib; encode it as RUNPATH so the
  # module can resolve libobs when loaded inside the sandbox.
  set_target_properties(what_overlay_plugin PROPERTIES
    BUILD_RPATH "/app/lib"
    INSTALL_RPATH "/app/lib"
  )
endif()

if(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED)
  target_sources(what_overlay_plugin PRIVATE
    src/panel/box_logic.cpp
    src/overlay_panel.cpp
  )
endif()

target_include_directories(what_overlay_plugin PRIVATE
  include
  ${OBS_INCLUDE_DIR}
  ${OBS_CONFIG_DIR}
  ${OBS_DEPS_INCLUDE}
)

if(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED)
  target_include_directories(what_overlay_plugin PRIVATE
    ${OBS_FRONTEND_API_INCLUDE_DIR}
  )
endif()

if(WHAT_OVERLAY_QT_DOCK_ENABLED)
  target_include_directories(what_overlay_plugin PRIVATE
    ${OBS_QT_FRAMEWORKS_DIR}/QtWidgets.framework/Versions/A/Headers
    ${OBS_QT_FRAMEWORKS_DIR}/QtGui.framework/Versions/A/Headers
    ${OBS_QT_FRAMEWORKS_DIR}/QtCore.framework/Versions/A/Headers
    ${OBS_QT_FRAMEWORKS_DIR}/QtNetwork.framework/Versions/A/Headers
  )
endif()

target_link_directories(what_overlay_plugin PRIVATE
  ${OBS_LIB_DIR}
)

if(APPLE)
  target_link_options(what_overlay_plugin PRIVATE "-F${OBS_LIB_DIR}")
  if(WHAT_OVERLAY_QT_DOCK_ENABLED)
    target_compile_options(what_overlay_plugin PRIVATE "-F${OBS_QT_FRAMEWORKS_DIR}")
    target_link_options(what_overlay_plugin PRIVATE "-F${OBS_QT_FRAMEWORKS_DIR}")
  endif()
endif()

if(APPLE)
  target_link_libraries(what_overlay_plugin
    "-framework libobs"
  )
else()
  find_library(OBS_LIB
    NAMES obs libobs
    HINTS ${OBS_LIB_DIR}
      /usr/lib/x86_64-linux-gnu
      /usr/lib64
      /usr/lib
      /usr/local/lib64
      /usr/local/lib
  )
  if(NOT OBS_LIB)
    message(FATAL_ERROR "Could not find libobs. Install OBS development headers/libraries or pass -DOBS_LIB_DIR=/path/to/lib.")
  endif()
  target_link_libraries(what_overlay_plugin
    ${OBS_LIB}
  )
endif()

if(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED)
  # Both macOS (.dylib) and Linux (.so) spellings -- searching only for .dylib meant a
  # Linux box with libobs-frontend-api.so sitting in OBS_LIB_DIR still reported the
  # library "not found" and silently disabled the frontend panel.
  foreach(_fe_candidate
    "${OBS_LIB_DIR}/obs-frontend-api.dylib"
    "${OBS_LIB_DIR}/libobs-frontend-api.dylib"
    "${OBS_LIB_DIR}/libobs-frontend-api.so"
    "${OBS_LIB_DIR}/obs-frontend-api.so"
  )
    if(NOT OBS_FRONTEND_API_LIB AND EXISTS "${_fe_candidate}")
      set(OBS_FRONTEND_API_LIB "${_fe_candidate}")
    endif()
  endforeach()
  if(NOT OBS_FRONTEND_API_LIB)
    message(WARNING "Frontend panel enabled but obs-frontend-api library not found under OBS_LIB_DIR='${OBS_LIB_DIR}'. Disabling frontend panel scaffold.")
    set(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED OFF)
  endif()
endif()

if(WHAT_OVERLAY_FRONTEND_PANEL_ENABLED)
  target_link_libraries(what_overlay_plugin
    ${OBS_FRONTEND_API_LIB}
  )
  target_compile_definitions(what_overlay_plugin PRIVATE
    WHAT_OVERLAY_HAS_FRONTEND_PANEL=1
  )
endif()

if(WHAT_OVERLAY_QT_DOCK_ENABLED)
  if(APPLE)
    target_link_libraries(what_overlay_plugin
      "-framework QtWidgets"
      "-framework QtGui"
      "-framework QtCore"
      "-framework QtNetwork"
    )
  else()
    target_link_libraries(what_overlay_plugin
      Qt6::Widgets Qt6::Gui Qt6::Core Qt6::Network
    )
  endif()
  target_compile_definitions(what_overlay_plugin PRIVATE
    WHAT_OVERLAY_HAS_QT_DOCK=1
  )
endif()

if(WHAT_OVERLAY_DEBUG)
  target_compile_definitions(what_overlay_plugin PRIVATE what_overlay_debug=1)
endif()

# OBS plugins typically need a specific output name
set_target_properties(what_overlay_plugin PROPERTIES
  PREFIX ""
  OUTPUT_NAME "what_overlay_plugin"
)

if(APPLE)
  set_target_properties(what_overlay_plugin PROPERTIES
    BUNDLE TRUE
    BUNDLE_EXTENSION "plugin"
    MACOSX_BUNDLE TRUE
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_LIST_DIR}/obs-plugin-Info.plist"
  )
endif()

if(WHAT_OVERLAY_BUILD_UNIT_TESTS)
  enable_testing()

  add_executable(what_caption_box_test_resize tests/test_browser_resize.cpp)
  target_include_directories(what_caption_box_test_resize PRIVATE include)
  add_test(NAME what_caption_box_test_resize COMMAND what_caption_box_test_resize)

  add_executable(what_caption_box_test_source tests/test_browser_source.cpp src/browser_source.cpp)
  target_include_directories(what_caption_box_test_source PRIVATE include ${OBS_INCLUDE_DIR} ${OBS_CONFIG_DIR} ${OBS_DEPS_INCLUDE})
  if(APPLE)
    target_link_options(what_caption_box_test_source PRIVATE "-F${OBS_LIB_DIR}")
    target_link_libraries(what_caption_box_test_source "-framework libobs")
    set_target_properties(what_caption_box_test_source PROPERTIES BUILD_RPATH "${OBS_LIB_DIR}")
  else()
    target_link_libraries(what_caption_box_test_source ${OBS_LIB})
  endif()
  add_test(NAME what_caption_box_test_source COMMAND what_caption_box_test_source)

  add_executable(what_overlay_test_text_wrap
    tests/test_text_wrap_utils.cpp
    src/layout/text_wrap_utils.cpp
  )
  target_include_directories(what_overlay_test_text_wrap PRIVATE
    include
  )
  add_test(NAME what_overlay_test_text_wrap COMMAND what_overlay_test_text_wrap)

  add_executable(what_overlay_test_color_font
    tests/test_color_font_utils.cpp
    src/render/color_font_utils.cpp
  )
  target_include_directories(what_overlay_test_color_font PRIVATE
    include
  )
  add_test(NAME what_overlay_test_color_font COMMAND what_overlay_test_color_font)

  add_executable(what_overlay_test_panel_box_logic
    tests/test_panel_box_logic.cpp
    src/panel/box_logic.cpp
  )
  target_include_directories(what_overlay_test_panel_box_logic PRIVATE
    include
  )
  add_test(NAME what_overlay_test_panel_box_logic COMMAND what_overlay_test_panel_box_logic)

  add_executable(what_overlay_test_overlay_label_policy
    tests/test_overlay_label_policy.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_overlay_label_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_overlay_label_policy COMMAND what_overlay_test_overlay_label_policy)

  add_executable(what_overlay_test_header_render_policy
    tests/test_header_render_policy.cpp
    src/layout/header_render_policy.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_header_render_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_header_render_policy COMMAND what_overlay_test_header_render_policy)

  add_executable(what_overlay_test_body_render_pipeline
    tests/test_body_render_pipeline.cpp
    src/layout/body_render_pipeline.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_body_render_pipeline PRIVATE
    include
  )
  add_test(NAME what_overlay_test_body_render_pipeline COMMAND what_overlay_test_body_render_pipeline)

  add_executable(what_overlay_test_source_render_policy
    tests/test_source_render_policy.cpp
    src/layout/source_render_policy.cpp
  )
  target_include_directories(what_overlay_test_source_render_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_source_render_policy COMMAND what_overlay_test_source_render_policy)

  add_executable(what_overlay_test_payload_ingest_policy
    tests/test_payload_ingest_policy.cpp
    src/pipeline/payload_ingest_policy.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_payload_ingest_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_payload_ingest_policy COMMAND what_overlay_test_payload_ingest_policy)

  add_executable(what_overlay_test_header_activation_policy
    tests/test_header_activation_policy.cpp
    src/pipeline/header_activation_policy.cpp
    src/layout/overlay_label_policy.cpp
    src/layout/source_render_policy.cpp
  )
  target_include_directories(what_overlay_test_header_activation_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_header_activation_policy COMMAND what_overlay_test_header_activation_policy)

  add_executable(what_overlay_test_header_source_sync_policy
    tests/test_header_source_sync_policy.cpp
    src/pipeline/header_source_sync_policy.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_header_source_sync_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_header_source_sync_policy COMMAND what_overlay_test_header_source_sync_policy)

  add_executable(what_overlay_test_transition_policy
    tests/test_transition_policy.cpp
    src/pipeline/transition_policy.cpp
  )
  target_include_directories(what_overlay_test_transition_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_transition_policy COMMAND what_overlay_test_transition_policy)

  add_executable(what_overlay_test_render_geometry_policy
    tests/test_render_geometry_policy.cpp
    src/pipeline/render_geometry_policy.cpp
    src/layout/header_render_policy.cpp
    src/layout/overlay_label_policy.cpp
  )
  target_include_directories(what_overlay_test_render_geometry_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_render_geometry_policy COMMAND what_overlay_test_render_geometry_policy)

  add_executable(what_overlay_test_runtime_adapter
    tests/test_runtime_adapter.cpp
    src/pipeline/runtime_adapter.cpp
    src/pipeline/header_activation_policy.cpp
    src/pipeline/payload_ingest_policy.cpp
    src/pipeline/render_geometry_policy.cpp
    src/pipeline/transition_policy.cpp
    src/pipeline/body_source_update_policy.cpp
    src/pipeline/body_fit_policy.cpp
    src/layout/overlay_label_policy.cpp
    src/layout/source_render_policy.cpp
    src/layout/header_render_policy.cpp
  )
  target_include_directories(what_overlay_test_runtime_adapter PRIVATE
    include
  )
  add_test(NAME what_overlay_test_runtime_adapter COMMAND what_overlay_test_runtime_adapter)

  add_executable(what_overlay_test_payload_json_parser
    tests/test_payload_json_parser.cpp
    src/pipeline/payload_json_parser.cpp
  )
  target_include_directories(what_overlay_test_payload_json_parser PRIVATE
    include
  )
  add_test(NAME what_overlay_test_payload_json_parser COMMAND what_overlay_test_payload_json_parser)

  add_executable(what_overlay_test_control_http_client
    tests/test_control_http_client.cpp
    src/pipeline/control_http_client.cpp
    src/pipeline/payload_json_parser.cpp
  )
  target_include_directories(what_overlay_test_control_http_client PRIVATE
    include
  )
  add_test(NAME what_overlay_test_control_http_client COMMAND what_overlay_test_control_http_client)

  add_executable(what_overlay_test_body_source_update_policy
    tests/test_body_source_update_policy.cpp
    src/pipeline/body_source_update_policy.cpp
  )
  target_include_directories(what_overlay_test_body_source_update_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_body_source_update_policy COMMAND what_overlay_test_body_source_update_policy)

  add_executable(what_overlay_test_body_fit_policy
    tests/test_body_fit_policy.cpp
    src/pipeline/body_fit_policy.cpp
  )
  target_include_directories(what_overlay_test_body_fit_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_body_fit_policy COMMAND what_overlay_test_body_fit_policy)

  add_executable(what_overlay_test_body_text_fit_inputs
    tests/test_body_text_fit_inputs.cpp
    src/pipeline/body_text_fit_inputs.cpp
  )
  target_include_directories(what_overlay_test_body_text_fit_inputs PRIVATE
    include
  )
  add_test(NAME what_overlay_test_body_text_fit_inputs COMMAND what_overlay_test_body_text_fit_inputs)

  add_executable(what_overlay_test_body_fit_path_parity
    tests/test_body_fit_path_parity.cpp
    src/pipeline/body_fit_policy.cpp
    src/pipeline/body_text_fit_inputs.cpp
  )
  target_include_directories(what_overlay_test_body_fit_path_parity PRIVATE
    include
  )
  add_test(NAME what_overlay_test_body_fit_path_parity COMMAND what_overlay_test_body_fit_path_parity)

  add_executable(what_overlay_test_legacy_wrap_policy
    tests/test_legacy_wrap_policy.cpp
    src/pipeline/legacy_wrap_policy.cpp
  )
  target_include_directories(what_overlay_test_legacy_wrap_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_legacy_wrap_policy COMMAND what_overlay_test_legacy_wrap_policy)

  add_executable(what_overlay_test_fit_decider
    tests/test_fit_decider.cpp
    src/layout/fit_decider.cpp
    src/layout/font_metrics.cpp
  )
  target_include_directories(what_overlay_test_fit_decider PRIVATE
    include
  )
  add_test(NAME what_overlay_test_fit_decider COMMAND what_overlay_test_fit_decider)

  add_executable(what_overlay_test_caption_freezer
    tests/test_caption_freezer.cpp
    src/layout/caption_freezer.cpp
    src/layout/visible_window_policy.cpp
    src/layout/fit_decider.cpp
    src/layout/font_metrics.cpp
  )
  target_include_directories(what_overlay_test_caption_freezer PRIVATE
    include
  )
  add_test(NAME what_overlay_test_caption_freezer COMMAND what_overlay_test_caption_freezer)

  add_executable(what_overlay_test_line_layout
    tests/test_line_layout.cpp
    src/layout/line_layout.cpp
    src/layout/visible_window_policy.cpp
    src/layout/font_metrics.cpp
  )
  target_include_directories(what_overlay_test_line_layout PRIVATE
    include
  )
  add_test(NAME what_overlay_test_line_layout COMMAND what_overlay_test_line_layout)

  add_executable(what_overlay_test_visible_window_policy
    tests/test_visible_window_policy.cpp
    src/layout/visible_window_policy.cpp
  )
  target_include_directories(what_overlay_test_visible_window_policy PRIVATE
    include
  )
  add_test(NAME what_overlay_test_visible_window_policy COMMAND what_overlay_test_visible_window_policy)
endif()
