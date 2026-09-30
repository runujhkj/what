#pragma once

#include <set>
#include <string>
#include <vector>

namespace what_overlay::layout {

std::string normalize_label_token(const std::string& value);

std::string resolve_effective_header(const std::string& payload_header,
                                     const std::string& configured_header,
                                     const std::string& current_header);

std::string select_active_header(const std::string& configured_header,
                                 const std::string& current_header);

std::set<std::string> canonical_label_set(const std::vector<std::string>& labels);

bool is_label_only_line(const std::string& line, const std::set<std::string>& labels);

std::string strip_leading_label(const std::string& line, const std::set<std::string>& labels);

std::vector<std::string> sanitize_body_lines(const std::vector<std::string>& lines,
                                             const std::vector<std::string>& labels);

}  // namespace what_overlay::layout
