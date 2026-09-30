#include "what_overlay/pipeline/body_fit_policy.h"

#include <cassert>
#include <cmath>
#include <vector>

using what_overlay::OverlayConfig;
using what_overlay::layout::FreezeRequest;
using what_overlay::pipeline::build_measured_freeze_request;
using what_overlay::pipeline::calc_max_lines_for_height;
using what_overlay::pipeline::resolve_effective_font_ui;
using what_overlay::pipeline::should_use_measured_layout;

int main() {
  {
    assert(resolve_effective_font_ui(7.05, true) == 7.05);
    assert(resolve_effective_font_ui(0.0, false) == 2.0);
  }

  {
    const int compact = calc_max_lines_for_height(140, 7.05, 6.0);
    const int roomy = calc_max_lines_for_height(500, 5.9, 6.0);
    assert(compact >= 1);
    assert(roomy >= compact);
  }

  {
    OverlayConfig cfg{};
    cfg.layout_engine = "measured_v1";
    assert(should_use_measured_layout(cfg));
    cfg.layout_engine = "legacy";
    assert(!should_use_measured_layout(cfg));
  }

  {
    OverlayConfig cfg{};
    cfg.font_family = "Helvetica";
    cfg.layout_engine = "measured_v1";
    const FreezeRequest req = build_measured_freeze_request(
        cfg,
        std::vector<std::string>{"test segment 1", "test segment 3"},
        870,
        270,
        5.9,
        7,
        true,
        6.0);
    assert(req.font.family == "Helvetica");
    assert(std::fabs(req.font.size_px - 35.4) < 0.0001);
    assert(req.width_px == 870);
    assert(req.max_lines >= 1);
    assert(req.max_lines <= 7);
    assert(req.no_word_split == true);
    assert(req.preserve_segment_units == false);
    assert(req.logical_lines.size() == 2);
  }

  return 0;
}
