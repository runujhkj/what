#include "what_overlay/pipeline/body_fit_policy.h"

#include <algorithm>
#include <cmath>

namespace what_overlay::pipeline {

double resolve_effective_font_ui(double configured_font_size_ui,
                                 bool auto_shrink_to_fit) {
  (void)auto_shrink_to_fit;
  return configured_font_size_ui > 0.0 ? configured_font_size_ui : 2.0;
}

int calc_max_lines_for_height(int height_px,
                              double ui_font_size,
                              double obs_font_scale_units) {
  const double line_h = std::max(8.0, std::max(0.1, ui_font_size) * std::max(1.0, obs_font_scale_units) * 1.2);
  return std::max(1, static_cast<int>(std::floor(static_cast<double>(std::max(1, height_px)) / line_h)));
}

bool should_use_measured_layout(const OverlayConfig& config) {
  return config.layout_engine == "measured_v1";
}

layout::FreezeRequest build_measured_freeze_request(
    const OverlayConfig& config,
    const std::vector<std::string>& logical_lines,
    int width_px,
    int height_px,
    double font_size_ui,
    int max_visible_lines,
    bool no_word_split,
    double obs_font_scale_units) {
  layout::FreezeRequest req;
  req.logical_lines = logical_lines;
  req.font.family = config.font_family;
  req.font.style = "";
  req.font.flags = 0;
  req.font.size_px = std::max(1.0, font_size_ui * std::max(1.0, obs_font_scale_units));
  req.width_px = std::max(24, width_px);
  req.max_lines = std::max(
      1,
      std::min(
          std::max(1, max_visible_lines),
          calc_max_lines_for_height(height_px, font_size_ui, obs_font_scale_units)));
  req.no_word_split = no_word_split;
  req.preserve_segment_units = false;
  return req;
}

}  // namespace what_overlay::pipeline
