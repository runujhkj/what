#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace what_overlay::layout {

std::vector<std::string> split_lines(const std::string& input);
std::string join_lines_from(const std::vector<std::string>& lines, size_t start_idx);
std::string join_lines_all(const std::vector<std::string>& lines);
std::string limit_tail_lines(const std::string& input, int max_lines);

}  // namespace what_overlay::layout
