#include "what_overlay/pipeline/legacy_wrap_policy.h"

#include <algorithm>
#include <cctype>
#include <cstring>

namespace what_overlay::pipeline {

namespace {

double ui_font_to_px(double ui_size, double obs_font_scale_units) {
  return std::max(1.0, ui_size * std::max(1.0, obs_font_scale_units));
}

double estimate_char_width_px(char c, double font_size_px) {
  const unsigned char uc = static_cast<unsigned char>(c);
  if (std::isspace(uc)) return font_size_px * 0.30;
  if (std::strchr("ilI|!.,:;'`", c)) return font_size_px * 0.26;
  if (std::strchr("mwMW@#%&", c)) return font_size_px * 0.80;
  if (std::isdigit(uc)) return font_size_px * 0.52;
  if (std::isupper(uc)) return font_size_px * 0.58;
  return font_size_px * 0.49;
}

double estimate_text_width_px(const std::string& text, double font_size_px) {
  double width = 0.0;
  for (char c : text) width += estimate_char_width_px(c, font_size_px);
  return width;
}

}  // namespace

std::string wrap_text_legacy_word_boundary(const std::string& input,
                                           int width_px,
                                           double font_size_ui,
                                           double wrap_slack,
                                           double obs_font_scale_units) {
  if (input.empty()) return "";
  const double font_size = ui_font_to_px(font_size_ui > 0.0 ? font_size_ui : 2.0, obs_font_scale_units);
  const double width_limit = std::max(24.0, static_cast<double>(width_px)) * wrap_slack;
  const double space_w = estimate_char_width_px(' ', font_size);
  std::string out;
  out.reserve(input.size() + 16);

  std::string line;
  double line_w = 0.0;
  std::string word;

  auto flush_word = [&]() {
    if (word.empty()) return;
    const double word_w = estimate_text_width_px(word, font_size);
    if (line.empty()) {
      line = word;
      line_w = word_w;
      word.clear();
      return;
    }
    if (line_w + space_w + word_w <= width_limit) {
      line.push_back(' ');
      line += word;
      line_w += space_w + word_w;
    } else {
      if (!out.empty()) out.push_back('\n');
      out += line;
      line = word;
      line_w = word_w;
    }
    word.clear();
  };

  auto flush_line = [&]() {
    flush_word();
    if (!out.empty()) out.push_back('\n');
    out += line;
    line.clear();
    line_w = 0.0;
  };

  for (size_t i = 0; i < input.size(); ++i) {
    const char c = input[i];
    if (c == '\n') {
      flush_line();
      continue;
    }
    if (std::isspace(static_cast<unsigned char>(c))) {
      flush_word();
      continue;
    }
    word.push_back(c);
  }
  flush_word();
  if (!line.empty()) {
    if (!out.empty()) out.push_back('\n');
    out += line;
  }
  return out;
}

std::string wrap_text_legacy_allow_split(const std::string& input,
                                         int width_px,
                                         double font_size_ui,
                                         double wrap_slack,
                                         double obs_font_scale_units) {
  if (input.empty()) return "";
  const double font_size = ui_font_to_px(font_size_ui > 0.0 ? font_size_ui : 2.0, obs_font_scale_units);
  const double width_limit = std::max(24.0, static_cast<double>(width_px)) * wrap_slack;
  std::string out;
  out.reserve(input.size() + 16);
  double col_w = 0.0;
  for (char c : input) {
    if (c == '\n') {
      out.push_back('\n');
      col_w = 0.0;
      continue;
    }
    const double ch_w = estimate_char_width_px(c, font_size);
    if (col_w + ch_w > width_limit && !out.empty() && out.back() != '\n') {
      out.push_back('\n');
      col_w = 0.0;
    }
    out.push_back(c);
    col_w += ch_w;
  }
  return out;
}

}  // namespace what_overlay::pipeline
