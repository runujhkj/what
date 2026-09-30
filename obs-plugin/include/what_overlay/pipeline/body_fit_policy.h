#pragma once

#include "what_overlay/layout/caption_freezer.h"
#include "what_overlay/overlay_config.h"

#include <string>
#include <vector>

namespace what_overlay::pipeline {

double resolve_effective_font_ui(double configured_font_size_ui,
                                 bool auto_shrink_to_fit = true);

int calc_max_lines_for_height(int height_px,
                              double ui_font_size,
                              double obs_font_scale_units = 6.0);

bool should_use_measured_layout(const OverlayConfig& config);

layout::FreezeRequest build_measured_freeze_request(
    const OverlayConfig& config,
    const std::vector<std::string>& logical_lines,
    int width_px,
    int height_px,
    double font_size_ui,
    int max_visible_lines,
    bool no_word_split,
    double obs_font_scale_units = 6.0);

}  // namespace what_overlay::pipeline
