#pragma once

#include <obs-module.h>

#include "overlay_client.h"
#include "overlay_config.h"
#include "overlay_state.h"

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace what_overlay {

struct OverlaySource {
  OverlayConfig config;
  OverlayClient client;
  obs_source_t* self_source = nullptr;
  obs_source_t* text_source = nullptr;
  obs_source_t* text_prev = nullptr;
  obs_source_t* text_enter = nullptr;
  obs_source_t* header_source = nullptr;
  obs_source_t* overflow_source = nullptr;
  std::mutex mutex;
  std::string current_text;
  std::string current_header;
  std::vector<std::string> current_lines;
  std::vector<std::string> current_segment_ids;
  std::vector<std::string> current_segments;
  std::vector<OverlayRenderedSpan> current_spans;
  std::string wrapped_text;
  std::string source_name;
  int pending_seq = -1;
  std::string pending_trace_id;
  int current_seq = -1;
  std::string current_trace_id;
  uint32_t text_color = 0xFFFFFFFF;
  uint32_t bg_color = 0x00000000;
  std::string pending_text;
  std::string pending_header;
  bool pending_has_header = false;
  std::vector<std::string> pending_lines;
  std::vector<std::string> pending_segment_ids;
  std::vector<std::string> pending_segments;
  std::vector<OverlayRenderedSpan> pending_spans;
  bool pending_has_lines = false;
  std::string pending_transition;
  std::string pending_enter_line;
  std::string pending_animation_mode;
  int pending_width_px = -1;
  int pending_height_px = -1;
  int pending_padding_px = -1;
  double pending_font_size_px = -1.0;
  bool pending_has_geometry = false;
  std::atomic<bool> has_pending{false};
  std::atomic<bool> alive{true};
  std::string delay_readback = "API delay readback: unavailable";
  uint64_t shared_state_version = 0;
  std::mutex delay_mutex;
  std::condition_variable delay_cv;
  std::thread delay_worker;
  bool delay_worker_stop = false;
  bool delay_dirty = false;
  int delay_target_seconds = 0;
  std::string delay_target_control_url = "http://127.0.0.1:8780";
  bool initialized_test_stream_default = false;
  bool test_stream_last_sent = false;
  uint64_t test_stream_retry_ns = 0;
  bool overflowed = false;
  bool animating = false;
  double anim_duration_s = 0.25;
  uint64_t anim_start_ns = 0;
  float anim_offset = 0.0f;
  float line_height = 36.0f;
  bool anim_shift_prev = true;
  bool anim_fade_only = false;
  bool auto_fit_ref_initialized = false;
  double auto_fit_ref_font_size = 3.0;
  int auto_fit_ref_content_height = 132;
  std::string last_geometry_debug_line;
  std::string last_margin_probe_debug_line;
  uint64_t last_margin_probe_log_ns = 0;
  // TODO: add font/texture handles from libobs for rendering.
};

// Returns the OBS source descriptor for registration.
const obs_source_info* get_overlay_source_info();

}  // namespace what_overlay
