#pragma once

#include "what_overlay/overlay_config.h"

#include <cstdint>
#include <string>

namespace what_overlay::pipeline {

struct BodySourceUpdateSpec {
  bool from_file = false;
  bool word_wrap = true;
  bool no_word_split = true;
  int custom_width = 640;
  bool extents = true;
  int extents_cx = 640;
  int extents_cy = 140;
  std::string align = "left";
  uint32_t color1 = 0xFFFFFFFF;
  uint32_t color2 = 0xFFFFFFFF;
  std::string font_face = "Helvetica";
  int font_units = 192;
  int font_flags = 0;
  std::string font_style = "";
};

BodySourceUpdateSpec build_body_source_update_spec(
    const OverlayConfig& config,
    int content_width,
    int content_height,
    double render_font_size_ui,
    uint32_t text_color_abgr,
    double obs_font_scale_units = 6.0);

}  // namespace what_overlay::pipeline
