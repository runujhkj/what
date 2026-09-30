#include "what_overlay/pipeline/body_fit_policy.h"
#include "what_overlay/pipeline/body_text_fit_inputs.h"
#include "what_overlay/overlay_config.h"

#include <cassert>
#include <string>
#include <vector>

using what_overlay::OverlayConfig;
using what_overlay::layout::FreezeRequest;
using what_overlay::pipeline::build_measured_freeze_request;
using what_overlay::pipeline::normalize_soft_breaks_for_fit;

namespace {

std::vector<std::string> split_lines_local(const std::string& input) {
  std::vector<std::string> lines;
  std::string current;
  for (char c : input) {
    if (c == '\n') {
      lines.push_back(current);
      current.clear();
    } else {
      current.push_back(c);
    }
  }
  lines.push_back(current);
  return lines;
}

}  // namespace

int main() {
  OverlayConfig cfg{};
  cfg.layout_engine = "measured_v1";
  cfg.font_family = "Helvetica";
  cfg.no_word_split = true;

  // Text-path body and lines-path body representing equivalent semantic content
  // under v0.1 reflow behavior.
  const std::string text_body = "test segment 1 test segment 3 test segment 5";
  const std::string lines_body = "test segment 1 test segment 3 test segment 5";

  const auto text_lines = split_lines_local(normalize_soft_breaks_for_fit(text_body));
  const auto lines_lines = split_lines_local(normalize_soft_breaks_for_fit(lines_body));

  const FreezeRequest text_req = build_measured_freeze_request(
      cfg, text_lines, 870, 270, 5.9, 7, true, 6.0);
  const FreezeRequest lines_req = build_measured_freeze_request(
      cfg, lines_lines, 870, 270, 5.9, 7, true, 6.0);

  // Core fit-policy fields should be identical regardless of source path.
  assert(text_req.font.family == lines_req.font.family);
  assert(text_req.font.size_px == lines_req.font.size_px);
  assert(text_req.width_px == lines_req.width_px);
  assert(text_req.max_lines == lines_req.max_lines);
  assert(text_req.no_word_split == lines_req.no_word_split);
  assert(text_req.preserve_segment_units == lines_req.preserve_segment_units);

  // Normalized logical lines must remain equivalent when semantic content
  // emitted by both paths is equivalent.
  assert(text_req.logical_lines == lines_req.logical_lines);
  assert(text_req.logical_lines.size() == 1);
  assert(text_req.logical_lines.front() == "test segment 1 test segment 3 test segment 5");

  return 0;
}
