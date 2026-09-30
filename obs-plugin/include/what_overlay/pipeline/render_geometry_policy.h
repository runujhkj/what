#pragma once

#include <string>

namespace what_overlay::pipeline {

struct RenderGeometryInput {
  int width_px = 0;
  int height_px = 0;
  int padding_x_px = 0;
  int padding_y_px = 0;
  bool outline_enabled = false;
  int outline_thickness_px = 0;
  double font_size_px = 0.0;
  std::string active_header;
};

struct RenderGeometry {
  int content_width_px = 24;
  int content_height_px = 24;
  int outline_px = 0;
  int top_extra_px = 0;
  float box_y = 0.0f;

  int label_height_px = 0;
  int header_top_pad = 10;
  float header_x = 0.0f;
  float header_y = 0.0f;

  float body_pad_x = 0.0f;
  float body_pad_y = 0.0f;

  float overflow_x = 0.0f;
  float overflow_y = 0.0f;
};

RenderGeometry compute_render_geometry(const RenderGeometryInput& input);

}  // namespace what_overlay::pipeline
