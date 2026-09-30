#include "what_overlay/layout/visible_window_policy.h"

#include <algorithm>
#include <cmath>

namespace what_overlay::layout {

int compute_max_visible_lines(int configured_max_lines,
                              int content_height_px,
                              double line_height_px) {
  const int cfg = std::max(1, configured_max_lines);
  const int content_h = std::max(1, content_height_px);
  const double line_h = std::max(1.0, line_height_px);
  const int height_limited =
      std::max(1, static_cast<int>(std::floor(content_h / line_h)));
  return std::max(1, std::min(cfg, height_limited));
}

VisibleWindowTrimResult trim_oldest_lines(std::vector<std::string>& lines,
                                          int max_visible_lines) {
  VisibleWindowTrimResult result;
  const int cap = std::max(1, max_visible_lines);
  if (static_cast<int>(lines.size()) <= cap) return result;
  result.overflowed = true;
  result.dropped = static_cast<int>(lines.size()) - cap;
  lines.erase(lines.begin(), lines.begin() + result.dropped);
  return result;
}

}  // namespace what_overlay::layout

