#include "what_overlay/layout/line_layout.h"
#include "what_overlay/layout/visible_window_policy.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>

namespace what_overlay::layout {
namespace {
int content_width(const LayoutRequest& req) {
  return std::max(24, req.width_px - (req.pad_x_px * 2));
}

int content_height(const LayoutRequest& req) {
  return std::max(24, req.height_px - (req.pad_y_px * 2));
}

double line_height(const FontSpec& font) {
  return std::max(8.0, font.size_px * 1.2);
}

std::vector<std::string> split_words(const std::string& line) {
  std::vector<std::string> out;
  std::stringstream ss(line);
  std::string word;
  while (ss >> word) out.push_back(word);
  return out;
}

double measure_line(const FontMetrics* fm, const FontSpec& font, const std::string& text) {
  return fm ? fm->measure_text_px(font, text) : (text.size() * font.size_px * 0.49);
}

}  // namespace

LineLayoutEngine::LineLayoutEngine(const FontMetrics* font_metrics)
    : font_metrics_(font_metrics) {}

AlignMode align_mode_from_string(const std::string& value) {
  if (value == "center") return AlignMode::kCenter;
  if (value == "right") return AlignMode::kRight;
  if (value == "justify") return AlignMode::kJustify;
  return AlignMode::kLeft;
}

LayoutResult LineLayoutEngine::layout(const LayoutRequest& req) const {
  LayoutResult out;
  out.content_width_px = content_width(req);
  out.content_height_px = content_height(req);
  out.line_height_px = line_height(req.font);
  const double wrap_width_px = static_cast<double>(out.content_width_px);
  const int max_lines = compute_max_visible_lines(
      req.max_lines, out.content_height_px, out.line_height_px);

  std::vector<std::string> raw_lines;
  std::stringstream block(req.text);
  std::string logical_line;
  while (std::getline(block, logical_line, '\n')) {
    const auto words = split_words(logical_line);
    std::string current;
    for (const std::string& w : words) {
      const std::string candidate = current.empty() ? w : (current + " " + w);
      const double width = measure_line(font_metrics_, req.font, candidate);
      if (current.empty() || width <= wrap_width_px) {
        current = candidate;
      } else {
        raw_lines.push_back(current);
        current = w;
      }
    }
    if (!current.empty()) raw_lines.push_back(current);
    if (words.empty()) raw_lines.emplace_back();
  }

  const VisibleWindowTrimResult trim = trim_oldest_lines(raw_lines, max_lines);
  out.overflowed = trim.overflowed;

  out.lines.reserve(raw_lines.size());
  for (std::size_t i = 0; i < raw_lines.size(); ++i) {
    LayoutLine line;
    line.text = raw_lines[i];
    while (!line.text.empty() && std::isspace(static_cast<unsigned char>(line.text.back()))) {
      line.text.pop_back();
    }

    line.measured_width_px = font_metrics_ ? font_metrics_->measure_text_px(req.font, line.text)
                                           : (line.text.size() * req.font.size_px * 0.49);
    line.x_px = static_cast<double>(req.pad_x_px);
    if (req.align == AlignMode::kCenter) {
      line.x_px = req.pad_x_px + std::max(0.0, (out.content_width_px - line.measured_width_px) / 2.0);
    } else if (req.align == AlignMode::kRight) {
      line.x_px = req.pad_x_px + std::max(0.0, out.content_width_px - line.measured_width_px);
    }
    line.y_px = req.pad_y_px + (static_cast<double>(i) * out.line_height_px);
    out.lines.push_back(std::move(line));
  }
  return out;
}

}  // namespace what_overlay::layout
