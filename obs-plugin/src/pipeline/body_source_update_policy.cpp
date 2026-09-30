#include "what_overlay/pipeline/body_source_update_policy.h"

#include <algorithm>
#include <cmath>

namespace what_overlay::pipeline {

BodySourceUpdateSpec build_body_source_update_spec(
    const OverlayConfig& config,
    int content_width,
    int content_height,
    double render_font_size_ui,
    uint32_t text_color_abgr,
    double obs_font_scale_units) {
  BodySourceUpdateSpec out;
  out.no_word_split = config.no_word_split;
  out.word_wrap = (config.layout_engine != "measured_v1");
  out.custom_width = std::max(24, content_width);
  out.extents_cx = out.custom_width;
  out.extents_cy = std::max(24, content_height);
  out.align = (config.align == "justify") ? "left" : config.align;
  out.color1 = text_color_abgr;
  out.color2 = text_color_abgr;
  out.font_face = config.font_family;
  const double font_units_raw = std::max(0.1, render_font_size_ui) * std::max(1.0, obs_font_scale_units);
  out.font_units = std::max(1, static_cast<int>(std::lround(font_units_raw)));
  return out;
}

}  // namespace what_overlay::pipeline
