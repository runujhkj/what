#include "what_overlay/pipeline/render_geometry_policy.h"

#include "what_overlay/layout/header_render_policy.h"

#include <algorithm>

namespace what_overlay::pipeline {

namespace {

int clamp_outline_px(bool enabled, int px) {
  if (!enabled) return 0;
  return std::max(1, std::min(24, px));
}

int content_width_px(const RenderGeometryInput& input) {
  return std::max(24, input.width_px - (input.padding_x_px * 2));
}

int content_height_px(const RenderGeometryInput& input) {
  return std::max(24, input.height_px - (input.padding_y_px * 2));
}

}  // namespace

RenderGeometry compute_render_geometry(const RenderGeometryInput& input) {
  RenderGeometry out;
  out.content_width_px = content_width_px(input);
  out.content_height_px = content_height_px(input);
  out.outline_px = clamp_outline_px(input.outline_enabled, input.outline_thickness_px);
  out.top_extra_px = layout::compute_top_extra_px(
      input.font_size_px,
      input.active_header,
      out.outline_px);
  out.box_y = static_cast<float>(out.top_extra_px);

  out.label_height_px = std::max(
      10,
      layout::compute_label_height_px(input.font_size_px, input.active_header));
  out.header_x = static_cast<float>(input.padding_x_px);
  out.header_y = std::max(
      0.0f,
      out.box_y - static_cast<float>(out.label_height_px + out.outline_px + 4));

  out.body_pad_x = static_cast<float>(std::max(0, input.padding_x_px));
  out.body_pad_y = out.box_y + static_cast<float>(std::max(0, input.padding_y_px));

  out.overflow_x = static_cast<float>(
      input.width_px - std::max(20, input.padding_x_px + 14));
  out.overflow_y = out.box_y + static_cast<float>(
      input.height_px - std::max(16, input.padding_y_px + 12));

  return out;
}

}  // namespace what_overlay::pipeline
