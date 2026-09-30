#pragma once

#include <string>

namespace what_overlay::pipeline {

std::string wrap_text_legacy_word_boundary(const std::string& input,
                                           int width_px,
                                           double font_size_ui,
                                           double wrap_slack = 2.10,
                                           double obs_font_scale_units = 6.0);

std::string wrap_text_legacy_allow_split(const std::string& input,
                                         int width_px,
                                         double font_size_ui,
                                         double wrap_slack = 2.10,
                                         double obs_font_scale_units = 6.0);

}  // namespace what_overlay::pipeline
