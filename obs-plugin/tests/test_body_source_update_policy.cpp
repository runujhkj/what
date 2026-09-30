#include "what_overlay/pipeline/body_source_update_policy.h"

#include <cassert>

using what_overlay::OverlayConfig;
using what_overlay::pipeline::BodySourceUpdateSpec;
using what_overlay::pipeline::build_body_source_update_spec;

int main() {
  {
    OverlayConfig cfg{};
    cfg.layout_engine = "measured_v1";
    cfg.align = "justify";
    cfg.no_word_split = true;
    cfg.font_family = "Helvetica";
    const BodySourceUpdateSpec spec =
        build_body_source_update_spec(cfg, 870, 270, 5.9, 0xFF00FF00, 6.0);
    assert(spec.from_file == false);
    assert(spec.word_wrap == false);
    assert(spec.no_word_split == true);
    assert(spec.custom_width == 870);
    assert(spec.extents_cx == 870);
    assert(spec.extents_cy == 270);
    assert(spec.align == "left");
    assert(spec.color1 == 0xFF00FF00);
    assert(spec.color2 == 0xFF00FF00);
    assert(spec.font_face == "Helvetica");
    assert(spec.font_units == 35);
  }

  {
    OverlayConfig cfg{};
    cfg.layout_engine = "legacy";
    cfg.align = "right";
    cfg.no_word_split = false;
    cfg.font_family = "Arial";
    const BodySourceUpdateSpec spec =
        build_body_source_update_spec(cfg, 12, 9, 0.0, 0xFFFFFFFF, 6.0);
    assert(spec.word_wrap == true);
    assert(spec.no_word_split == false);
    assert(spec.custom_width == 24);
    assert(spec.extents_cx == 24);
    assert(spec.extents_cy == 24);
    assert(spec.align == "right");
    assert(spec.font_face == "Arial");
    assert(spec.font_units >= 1);
  }

  return 0;
}
