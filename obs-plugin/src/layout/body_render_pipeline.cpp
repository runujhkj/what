#include "what_overlay/layout/body_render_pipeline.h"

#include "what_overlay/layout/overlay_label_policy.h"

#include <algorithm>
#include <cctype>
#include <set>
#include <string>
#include <vector>

namespace what_overlay::layout {

namespace {

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
  lines.push_back(current);
  return lines;
}

std::string join_lines_all(const std::vector<std::string>& lines) {
  std::string out;
  for (size_t i = 0; i < lines.size(); ++i) {
    if (i != 0) out.push_back('\n');
    out += lines[i];
  }
  return out;
}

std::string join_lines_spaced(const std::vector<std::string>& lines) {
  std::string out;
  for (const auto& line : lines) {
    if (line.empty()) continue;
    if (!out.empty()) out.push_back(' ');
    out += line;
  }
  return out;
}

std::string maybe_uppercase(std::string value, bool uppercase) {
  if (!uppercase) return value;
  for (char& c : value) {
    c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  }
  return value;
}

std::string strip_leading_header_line(const std::string& text, const std::string& header) {
  if (header.empty() || text.empty()) return text;
  const std::string normalized_header = normalize_label_token(header);
  if (normalized_header.empty()) return text;
  const std::size_t line_end = text.find('\n');
  const std::string first_line = (line_end == std::string::npos) ? text : text.substr(0, line_end);
  if (normalize_label_token(first_line) != normalized_header) return text;
  if (line_end == std::string::npos) return "";
  return text.substr(line_end + 1);
}

std::vector<std::string> strip_leading_header_line_vec(
    const std::vector<std::string>& lines, const std::string& header) {
  if (header.empty() || lines.empty()) return lines;
  const std::string normalized_header = normalize_label_token(header);
  if (normalized_header.empty()) return lines;
  if (normalize_label_token(lines.front()) != normalized_header) return lines;
  return std::vector<std::string>(lines.begin() + 1, lines.end());
}

std::string strip_any_leading_header_line(const std::string& text,
                                          const std::string& preferred_header,
                                          const std::string& fallback_header) {
  std::string out = strip_leading_header_line(text, preferred_header);
  out = strip_leading_header_line(out, fallback_header);
  return out;
}

std::vector<std::string> strip_any_leading_header_line_vec(
    const std::vector<std::string>& lines, const std::string& preferred_header,
    const std::string& fallback_header) {
  std::vector<std::string> out = strip_leading_header_line_vec(lines, preferred_header);
  out = strip_leading_header_line_vec(out, fallback_header);
  return out;
}

std::vector<std::string> sanitize_body_lines_remove_header_only(
    const std::vector<std::string>& lines, const std::string& preferred_header,
    const std::string& fallback_header) {
  return sanitize_body_lines(lines, {preferred_header, fallback_header});
}

std::string sanitize_body_text_remove_header_only(const std::string& text,
                                                  const std::string& preferred_header,
                                                  const std::string& fallback_header) {
  std::vector<std::string> lines;
  std::string current;
  for (char c : text) {
    if (c == '\n') {
      lines.push_back(current);
      current.clear();
      continue;
    }
    current.push_back(c);
  }
  if (!current.empty() || text.find('\n') != std::string::npos) lines.push_back(current);
  const auto cleaned = sanitize_body_lines_remove_header_only(lines, preferred_header, fallback_header);
  return join_lines_all(cleaned);
}

std::string remove_standalone_label_body(const std::string& text, const std::string& preferred_header,
                                         const std::string& fallback_header) {
  const auto labels = canonical_label_set({preferred_header, fallback_header, "mic", "desktop"});
  if (is_label_only_line(text, labels)) return "";
  return text;
}

void prune_leading_label_lines(std::vector<std::string>& lines, const std::string& preferred_header,
                               const std::string& fallback_header) {
  const auto labels = canonical_label_set({preferred_header, fallback_header, "mic", "desktop"});
  auto is_label = [&](const std::string& raw) { return raw.empty() || is_label_only_line(raw, labels); };
  while (!lines.empty() && is_label(lines.front())) {
    lines.erase(lines.begin());
  }
}

std::vector<std::string> scrub_label_tokens_every_line(const std::vector<std::string>& lines,
                                                       const std::string& preferred_header,
                                                       const std::string& fallback_header) {
  const auto labels = canonical_label_set({preferred_header, fallback_header, "mic", "desktop"});
  std::vector<std::string> out;
  out.reserve(lines.size());
  for (const auto& raw : lines) {
    std::string s = strip_leading_label(raw, labels);
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) s.pop_back();
    if (!s.empty()) out.push_back(s);
  }
  return out;
}

}  // namespace

LineBreakPolicy parse_line_break_policy(const std::string& value) {
  const std::string normalized = normalize_label_token(value);
  if (normalized == "preserve_input" || normalized == "preserveinput" ||
      normalized == "preserve_input_line_breaks" || normalized == "preserveinputlinebreaks") {
    return LineBreakPolicy::kPreserveInput;
  }
  if (normalized == "break_on_gap_ms" || normalized == "breakongapms") {
    return LineBreakPolicy::kBreakOnGapMs;
  }
  if (normalized == "break_on_semantic_boundary" || normalized == "breakonsemanticboundary") {
    return LineBreakPolicy::kBreakOnSemanticBoundary;
  }
  return LineBreakPolicy::kReflowAll;
}

std::string preprocess_body_text(const std::string& text,
                                 const std::string& preferred_header,
                                 const std::string& fallback_header) {
  std::string body = strip_any_leading_header_line(text, preferred_header, fallback_header);
  body = sanitize_body_text_remove_header_only(body, preferred_header, fallback_header);
  body = remove_standalone_label_body(body, preferred_header, fallback_header);
  if (!body.empty()) {
    std::vector<std::string> body_lines = split_lines(body);
    prune_leading_label_lines(body_lines, preferred_header, fallback_header);
    body_lines = scrub_label_tokens_every_line(body_lines, preferred_header, fallback_header);
    body = join_lines_all(body_lines);
  }
  return body;
}

std::vector<std::string> preprocess_body_lines(const std::vector<std::string>& lines,
                                               const std::string& preferred_header,
                                               const std::string& fallback_header) {
  std::vector<std::string> visible_lines =
      strip_any_leading_header_line_vec(lines, preferred_header, fallback_header);
  visible_lines = sanitize_body_lines_remove_header_only(visible_lines, preferred_header, fallback_header);
  prune_leading_label_lines(visible_lines, preferred_header, fallback_header);
  std::vector<std::string> filtered_lines;
  filtered_lines.reserve(visible_lines.size());
  for (const auto& line : visible_lines) {
    const std::string keep = remove_standalone_label_body(line, preferred_header, fallback_header);
    if (!keep.empty()) filtered_lines.push_back(keep);
  }
  return filtered_lines;
}

BodyRenderOutput postprocess_visible_text(const std::string& visible_text,
                                          const std::string& preferred_header,
                                          const std::string& fallback_header) {
  BodyRenderOutput out;
  out.lines = split_lines(visible_text);
  prune_leading_label_lines(out.lines, preferred_header, fallback_header);
  out.lines = scrub_label_tokens_every_line(out.lines, preferred_header, fallback_header);
  out.text = join_lines_all(out.lines);
  const std::string lower = normalize_label_token(out.text);
  out.contains_label_token = (lower.find("mic") != std::string::npos ||
                              lower.find("desktop") != std::string::npos);
  return out;
}

std::string prepare_body_text_input(const std::string& text,
                                    const std::string& preferred_header,
                                    const std::string& fallback_header,
                                    bool uppercase) {
  return maybe_uppercase(
      preprocess_body_text(text, preferred_header, fallback_header),
      uppercase);
}

std::string prepare_body_lines_input(const std::vector<std::string>& lines,
                                     const std::string& preferred_header,
                                     const std::string& fallback_header,
                                     bool uppercase,
                                     LineBreakPolicy policy) {
  const std::vector<std::string> cleaned = preprocess_body_lines(lines, preferred_header, fallback_header);
  std::string composed;
  switch (policy) {
    case LineBreakPolicy::kPreserveInput:
      composed = join_lines_all(cleaned);
      break;
    case LineBreakPolicy::kBreakOnGapMs:
    case LineBreakPolicy::kBreakOnSemanticBoundary:
      // Future behavior hook: these modes currently defer to v0.1 reflow-all.
      // Once gap/semantic signals are available, switch these to selective
      // hard-break insertion while preserving width-fill by default.
      [[fallthrough]];
    case LineBreakPolicy::kReflowAll:
    default:
      composed = join_lines_spaced(cleaned);
      break;
  }
  return maybe_uppercase(
      composed,
      uppercase);
}

BodyRenderOutput finalize_body_visible_text(const std::string& visible_text,
                                            const std::string& preferred_header,
                                            const std::string& fallback_header) {
  return postprocess_visible_text(visible_text, preferred_header, fallback_header);
}

}  // namespace what_overlay::layout
