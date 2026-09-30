#pragma once

#include "font_metrics.h"

#include <string>
#include <vector>

namespace what_overlay::layout {

enum class AlignMode {
  kLeft,
  kCenter,
  kRight,
  kJustify,
};

struct LayoutLine {
  std::string text;
  double measured_width_px = 0.0;
  double x_px = 0.0;
  double y_px = 0.0;
};

struct LayoutRequest {
  std::string text;
  FontSpec font;
  AlignMode align = AlignMode::kLeft;
  int width_px = 640;
  int height_px = 140;
  int pad_x_px = 6;
  int pad_y_px = 4;
  int max_lines = 3;
  bool no_word_split = true;
};

struct LayoutResult {
  std::vector<LayoutLine> lines;
  int content_width_px = 0;
  int content_height_px = 0;
  double line_height_px = 0.0;
  bool overflowed = false;
};

class LineLayoutEngine {
 public:
  explicit LineLayoutEngine(const FontMetrics* font_metrics);

  LayoutResult layout(const LayoutRequest& request) const;

 private:
  const FontMetrics* font_metrics_;
};

AlignMode align_mode_from_string(const std::string& value);

}  // namespace what_overlay::layout
