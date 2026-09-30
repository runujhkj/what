#include "what_overlay/layout/overlay_label_policy.h"

#include <algorithm>
#include <cctype>

namespace what_overlay::layout {

namespace {

std::string trim_ascii(std::string value) {
  while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front()))) value.erase(value.begin());
  while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back();
  return value;
}

bool starts_with_token_ci(const std::string& input, const std::string& token, size_t start) {
  if (start + token.size() > input.size()) return false;
  for (size_t i = 0; i < token.size(); ++i) {
    const char a = static_cast<char>(std::tolower(static_cast<unsigned char>(input[start + i])));
    if (a != token[i]) return false;
  }
  return true;
}

bool is_separator_or_space(char c) {
  return std::isspace(static_cast<unsigned char>(c)) || c == ':' || c == '-' || c == '|';
}

std::string strip_single_prefix(const std::string& raw, const std::string& label) {
  if (label.empty()) return raw;
  size_t i = 0;
  while (i < raw.size() && std::isspace(static_cast<unsigned char>(raw[i]))) ++i;
  if (!starts_with_token_ci(raw, label, i)) return raw;
  size_t j = i + label.size();
  if (j < raw.size() && std::isalnum(static_cast<unsigned char>(raw[j]))) return raw;
  bool had_sep = false;
  while (j < raw.size() && is_separator_or_space(raw[j])) {
    had_sep = true;
    ++j;
  }
  if (!had_sep && j < raw.size()) return raw;
  std::string out = (j < raw.size()) ? raw.substr(j) : std::string{};
  return trim_ascii(out);
}

}  // namespace

std::string normalize_label_token(const std::string& value) {
  std::string s = trim_ascii(value);
  while (!s.empty() && (s.back() == ':' || s.back() == '-')) {
    s.pop_back();
    s = trim_ascii(s);
  }
  std::transform(s.begin(), s.end(), s.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return s;
}

std::string resolve_effective_header(const std::string& payload_header,
                                     const std::string& configured_header,
                                     const std::string& current_header) {
  if (!normalize_label_token(payload_header).empty()) return payload_header;
  if (!normalize_label_token(configured_header).empty()) return configured_header;
  return current_header;
}

std::string select_active_header(const std::string& configured_header,
                                 const std::string& current_header) {
  if (!normalize_label_token(configured_header).empty()) return configured_header;
  if (!normalize_label_token(current_header).empty()) return current_header;
  return "";
}

std::set<std::string> canonical_label_set(const std::vector<std::string>& labels) {
  std::set<std::string> out;
  for (const auto& raw : labels) {
    const std::string n = normalize_label_token(raw);
    if (!n.empty()) out.insert(n);
  }
  return out;
}

bool is_label_only_line(const std::string& line, const std::set<std::string>& labels) {
  const std::string n = normalize_label_token(line);
  return !n.empty() && labels.find(n) != labels.end();
}

std::string strip_leading_label(const std::string& line, const std::set<std::string>& labels) {
  std::string out = line;
  for (const auto& label : labels) {
    out = strip_single_prefix(out, label);
  }
  return trim_ascii(out);
}

std::vector<std::string> sanitize_body_lines(const std::vector<std::string>& lines,
                                             const std::vector<std::string>& labels_in) {
  std::vector<std::string> labels = labels_in;
  labels.push_back("mic");
  labels.push_back("desktop");
  const std::set<std::string> label_set = canonical_label_set(labels);
  std::vector<std::string> out;
  out.reserve(lines.size());
  for (const auto& raw : lines) {
    const std::string trimmed = trim_ascii(raw);
    if (trimmed.empty()) continue;
    if (is_label_only_line(trimmed, label_set)) continue;
    const std::string stripped = strip_leading_label(trimmed, label_set);
    if (stripped.empty()) continue;
    if (is_label_only_line(stripped, label_set)) continue;
    out.push_back(stripped);
  }
  return out;
}

}  // namespace what_overlay::layout
