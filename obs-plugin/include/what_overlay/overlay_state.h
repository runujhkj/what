#pragma once

#include "what_overlay/overlay_config.h"

#include <cstdint>
#include <string>
#include <vector>

namespace what_overlay {

struct OverlayRenderedSpan {
  size_t start = 0;
  size_t end = 0;
  std::string segment_id;
};

struct OverlayStateSnapshot {
  OverlayConfig config;
  std::string delay_readback = "API delay readback: unavailable";
  double effective_font_size_px = 3.0;
  std::string rendered_text;
  std::vector<std::string> rendered_segment_ids;
  std::vector<std::string> rendered_segments;
  std::vector<OverlayRenderedSpan> rendered_spans;
  uint64_t version = 0;
};

// Returns a thread-safe snapshot of the shared overlay state.
OverlayStateSnapshot overlay_state_snapshot();

// Replaces shared config and returns the new state version.
uint64_t overlay_state_set_config(const OverlayConfig& config);

// Updates only geometry/padding fields and returns the new state version.
uint64_t overlay_state_set_geometry(int width_px, int height_px, int pad_x_px, int pad_y_px);

// Updates only delay seconds and returns the new state version.
uint64_t overlay_state_set_delay_seconds(int delay_seconds);

// Updates delay readback text and returns the new state version.
uint64_t overlay_state_set_delay_readback(const std::string& delay_readback);

// Updates currently rendered output text and returns the new state version.
uint64_t overlay_state_set_rendered_text(const std::string& rendered_text);

// Updates rendered output text and segments and returns the new state version.
uint64_t overlay_state_set_rendered_output(
    const std::string& rendered_text,
    const std::vector<std::string>& rendered_segment_ids,
    const std::vector<std::string>& rendered_segments,
    const std::vector<OverlayRenderedSpan>& rendered_spans);

// Updates current effective (rendered) font size and returns new state version.
uint64_t overlay_state_set_effective_font_size(double effective_font_size_px);

}  // namespace what_overlay
