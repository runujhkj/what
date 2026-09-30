#include "what_overlay/pipeline/render_geometry_policy.h"

#include <cassert>

using what_overlay::pipeline::RenderGeometryInput;
using what_overlay::pipeline::compute_render_geometry;

int main() {
  {
    RenderGeometryInput in{};
    in.width_px = 640;
    in.height_px = 140;
    in.padding_x_px = 6;
    in.padding_y_px = 4;
    in.outline_enabled = true;
    in.outline_thickness_px = 3;
    in.font_size_px = 7.05;
    in.active_header = "";
    const auto g = compute_render_geometry(in);
    assert(g.top_extra_px == 0);
    assert(g.box_y == 0.0f);
    assert(g.outline_px == 3);
    assert(g.content_width_px == 628);
    assert(g.content_height_px == 132);
  }

  {
    RenderGeometryInput in{};
    in.width_px = 640;
    in.height_px = 140;
    in.padding_x_px = 6;
    in.padding_y_px = 4;
    in.outline_enabled = true;
    in.outline_thickness_px = 3;
    in.font_size_px = 7.05;
    in.active_header = "Desktop";
    const auto g = compute_render_geometry(in);
    assert(g.top_extra_px == 39);
    assert(g.box_y == 39.0f);
    assert(g.label_height_px == 18);
    assert(g.header_y == 14.0f);
    assert(g.body_pad_x == 6.0f);
    assert(g.body_pad_y == 43.0f);
    assert(g.overflow_x == 620.0f);
    assert(g.overflow_y == 163.0f);
  }

  {
    RenderGeometryInput in{};
    in.width_px = 640;
    in.height_px = 140;
    in.padding_x_px = 6;
    in.padding_y_px = 4;
    in.outline_enabled = true;
    in.outline_thickness_px = 3;
    in.font_size_px = 17.95;
    in.active_header = "Mic";
    const auto g = compute_render_geometry(in);
    assert(g.top_extra_px == 66);
    assert(g.box_y == 66.0f);
    assert(g.label_height_px == 45);
    assert(g.header_y == 14.0f);
  }

  return 0;
}
