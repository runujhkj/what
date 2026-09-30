#include "what_overlay/layout/text_wrap_utils.h"

namespace what_overlay::layout {

std::vector<std::string> split_lines(const std::string& input) {
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
  if (!current.empty() || input.find('\n') != std::string::npos) {
    lines.push_back(current);
  }
  return lines;
}

std::string join_lines_from(const std::vector<std::string>& lines, size_t start_idx) {
  std::string out;
  for (size_t i = start_idx; i < lines.size(); ++i) {
    if (!out.empty()) out.push_back('\n');
    out += lines[i];
  }
  return out;
}

std::string join_lines_all(const std::vector<std::string>& lines) {
  return join_lines_from(lines, 0);
}

std::string limit_tail_lines(const std::string& input, int max_lines) {
  if (max_lines <= 0) return input;
  const auto lines = split_lines(input);
  if (static_cast<int>(lines.size()) <= max_lines) return input;
  return join_lines_from(lines, lines.size() - static_cast<size_t>(max_lines));
}

}  // namespace what_overlay::layout
