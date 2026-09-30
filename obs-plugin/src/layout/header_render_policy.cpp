#include "what_overlay/layout/header_render_policy.h"

#include "what_overlay/layout/overlay_label_policy.h"

#include <algorithm>
#include <cmath>

namespace what_overlay::layout {

namespace {
constexpr double kObsFontScale = 6.0;
}

int compute_label_font_units(double font_size_px, const std::string& active_header) {
  if (normalize_label_token(active_header).empty()) return 0;
  const double caption_units = std::max(6.0, std::max(0.1, font_size_px) * kObsFontScale);
  return std::max(8, static_cast<int>(std::lround(caption_units / 3.0)));
}

int compute_label_height_px(double font_size_px, const std::string& active_header) {
  const int units = compute_label_font_units(font_size_px, active_header);
  if (units <= 0) return 0;
  return std::max(10, static_cast<int>(std::lround(static_cast<double>(units) * 1.25)));
}

int compute_top_extra_px(double font_size_px,
                         const std::string& active_header,
                         int outline_px) {
  const int label_h = compute_label_height_px(font_size_px, active_header);
  if (label_h <= 0) return 0;
  const int gap = 8;
  const int top_pad = 10;
  return label_h + gap + std::max(0, outline_px) + top_pad;
}

}  // namespace what_overlay::layout
