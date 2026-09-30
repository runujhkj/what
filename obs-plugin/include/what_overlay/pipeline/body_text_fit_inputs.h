#pragma once

#include <string>

namespace what_overlay::pipeline {

std::string normalize_soft_breaks_for_fit(const std::string& input);

std::string limit_tail_lines_for_fit(const std::string& input, int max_lines);

}  // namespace what_overlay::pipeline
