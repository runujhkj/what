#pragma once

#include <string>

namespace what_overlay::layout {

int compute_label_font_units(double font_size_px, const std::string& active_header);

int compute_label_height_px(double font_size_px, const std::string& active_header);

int compute_top_extra_px(double font_size_px,
                         const std::string& active_header,
                         int outline_px);

}  // namespace what_overlay::layout

