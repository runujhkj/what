#pragma once

#include <string>
#include <vector>

namespace what_overlay::layout {

int compute_max_visible_lines(int configured_max_lines,
                              int content_height_px,
                              double line_height_px);

struct VisibleWindowTrimResult {
  bool overflowed = false;
  int dropped = 0;
};

VisibleWindowTrimResult trim_oldest_lines(std::vector<std::string>& lines,
                                          int max_visible_lines);

}  // namespace what_overlay::layout

