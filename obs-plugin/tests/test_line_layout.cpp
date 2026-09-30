#include "what_overlay/layout/line_layout.h"

#include <cassert>
#include <vector>

using what_overlay::layout::AlignMode;
using what_overlay::layout::LayoutRequest;
using what_overlay::layout::LineLayoutEngine;

namespace {

std::vector<std::string> extract_lines(
    const std::vector<what_overlay::layout::LayoutLine>& lines) {
  std::vector<std::string> out;
  out.reserve(lines.size());
  for (const auto& line : lines) out.push_back(line.text);
  return out;
}

}  // namespace

int main() {
  LineLayoutEngine engine(nullptr);

  LayoutRequest baseline_req{};
  baseline_req.text =
      "test segment 1 test segment 3 test segment 5 test segment 7 test segment 9 test segment 11";
  baseline_req.font.size_px = 32.0;
  baseline_req.align = AlignMode::kLeft;
  baseline_req.width_px = 260;
  baseline_req.height_px = 4000;
  baseline_req.pad_x_px = 6;
  baseline_req.pad_y_px = 4;
  baseline_req.max_lines = 99;

  const auto baseline = engine.layout(baseline_req);
  const auto baseline_lines = extract_lines(baseline.lines);
  assert(!baseline_lines.empty());

  LayoutRequest capped_req = baseline_req;
  capped_req.max_lines = 3;
  const auto capped = engine.layout(capped_req);
  const auto capped_lines = extract_lines(capped.lines);
  assert(capped.overflowed);
  assert(capped_lines.size() == 3);
  assert(baseline_lines.size() > capped_lines.size());
  {
    const std::size_t start = baseline_lines.size() - capped_lines.size();
    for (std::size_t i = 0; i < capped_lines.size(); ++i) {
      assert(capped_lines[i] == baseline_lines[start + i]);
    }
  }

  LayoutRequest height_limited_req = baseline_req;
  height_limited_req.max_lines = 99;
  // With 32px font, line-height is 38.4px; content_h=80 gives floor(80/38.4)=2
  height_limited_req.height_px = 88;
  height_limited_req.pad_y_px = 4;
  const auto height_limited = engine.layout(height_limited_req);
  assert(height_limited.lines.size() == 2);

  return 0;
}

