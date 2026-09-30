#include "what_overlay/pipeline/body_text_fit_inputs.h"

#include <cctype>
#include <string>
#include <vector>

namespace what_overlay::pipeline {

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

std::string join_lines_local(const std::vector<std::string>& lines, size_t start_idx) {
  std::string out;
  for (size_t i = start_idx; i < lines.size(); ++i) {
    if (!out.empty()) out.push_back('\n');
    out += lines[i];
  }
  return out;
}

}  // namespace

std::string normalize_soft_breaks_for_fit(const std::string& input) {
  std::string out;
  out.reserve(input.size());
  size_t i = 0;
  while (i < input.size()) {
    const char c = input[i];
    if (c == '\r') {
      ++i;
      continue;
    }
    if (c == '\n') {
      size_t run = 0;
      while (i < input.size() && input[i] == '\n') {
        ++run;
        ++i;
      }
      (void)run;
      while (!out.empty() && out.back() == ' ') out.pop_back();
      if (!out.empty() && out.back() != '\n') out.push_back('\n');
      continue;
    }
    if (std::isspace(static_cast<unsigned char>(c))) {
      if (!out.empty() && out.back() != ' ' && out.back() != '\n') out.push_back(' ');
      ++i;
      continue;
    }
    out.push_back(c);
    ++i;
  }
  while (!out.empty() && out.back() == ' ') out.pop_back();
  while (!out.empty() && out.back() == '\n') out.pop_back();
  return out;
}

std::string limit_tail_lines_for_fit(const std::string& input, int max_lines) {
  if (max_lines <= 0) return input;
  const auto lines = split_lines_local(input);
  if (static_cast<int>(lines.size()) <= max_lines) return input;
  return join_lines_local(lines, lines.size() - static_cast<size_t>(max_lines));
}

}  // namespace what_overlay::pipeline
