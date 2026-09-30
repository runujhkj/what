#include "what_overlay/pipeline/payload_json_parser.h"

#include <cctype>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace what_overlay::pipeline {

namespace {

std::string json_unescape(const std::string& value) {
  std::string out;
  out.reserve(value.size());
  for (size_t i = 0; i < value.size(); ++i) {
    char c = value[i];
    if (c != '\\' || i + 1 >= value.size()) {
      out.push_back(c);
      continue;
    }
    char n = value[++i];
    switch (n) {
      case 'n': out.push_back('\n'); break;
      case 'r': out.push_back('\r'); break;
      case 't': out.push_back('\t'); break;
      case '"': out.push_back('"'); break;
      case '\\': out.push_back('\\'); break;
      default: out.push_back(n); break;
    }
  }
  return out;
}

double parse_loose_number(const std::string& value, double fallback) {
  if (value.empty()) return fallback;
  size_t start = std::string::npos;
  for (size_t i = 0; i < value.size(); ++i) {
    const char c = value[i];
    if (std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == '+') {
      start = i;
      break;
    }
  }
  if (start == std::string::npos) return fallback;
  size_t end = start;
  bool saw_dot = false;
  while (end < value.size()) {
    const char c = value[end];
    if (std::isdigit(static_cast<unsigned char>(c)) || ((c == '-' || c == '+') && end == start)) {
      end++;
      continue;
    }
    if (c == '.' && !saw_dot) {
      saw_dot = true;
      end++;
      continue;
    }
    break;
  }
  if (end <= start) return fallback;
  try {
    return std::stod(value.substr(start, end - start));
  } catch (...) {
    return fallback;
  }
}

}  // namespace

std::string json_get_string(const std::string& json, const std::string& key) {
  const std::string needle = "\"" + key + "\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return "";
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) return "";
  pos += 1;
  while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) pos++;
  if (pos >= json.size() || json[pos] != '"') return "";
  pos += 1;
  std::string value;
  while (pos < json.size()) {
    char c = json[pos++];
    if (c == '\\' && pos < json.size()) {
      value.push_back('\\');
      value.push_back(json[pos++]);
      continue;
    }
    if (c == '"') break;
    value.push_back(c);
  }
  return json_unescape(value);
}

bool json_has_key(const std::string& json, const std::string& key) {
  const std::string needle = "\"" + key + "\"";
  return json.find(needle) != std::string::npos;
}

std::vector<std::string> json_get_string_array(const std::string& json, const std::string& key) {
  std::vector<std::string> out;
  const std::string needle = "\"" + key + "\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return out;
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) return out;
  pos += 1;
  while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) pos++;
  if (pos >= json.size() || json[pos] != '[') return out;
  pos += 1;
  while (pos < json.size()) {
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) pos++;
    if (pos >= json.size()) break;
    if (json[pos] == ']') break;
    if (json[pos] == ',') {
      pos += 1;
      continue;
    }
    if (json[pos] != '"') {
      pos += 1;
      continue;
    }
    pos += 1;
    std::string value;
    while (pos < json.size()) {
      char c = json[pos++];
      if (c == '\\' && pos < json.size()) {
        value.push_back('\\');
        value.push_back(json[pos++]);
        continue;
      }
      if (c == '"') break;
      value.push_back(c);
    }
    out.push_back(json_unescape(value));
  }
  return out;
}

std::vector<JsonSegment> json_get_segments(const std::string& json, const std::string& key) {
  std::vector<JsonSegment> out;
  const std::string needle = "\"" + key + "\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return out;
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) return out;
  pos = json.find('[', pos);
  if (pos == std::string::npos) return out;
  size_t i = pos + 1;
  while (i < json.size()) {
    while (i < json.size() && std::isspace(static_cast<unsigned char>(json[i]))) i++;
    if (i >= json.size() || json[i] == ']') break;
    if (json[i] == ',') {
      i++;
      continue;
    }
    if (json[i] != '{') {
      i++;
      continue;
    }
    int depth = 0;
    size_t start = i;
    while (i < json.size()) {
      if (json[i] == '{') depth++;
      else if (json[i] == '}') {
        depth--;
        if (depth == 0) {
          i++;
          break;
        }
      }
      i++;
    }
    const std::string obj = json.substr(start, i - start);
    JsonSegment seg;
    seg.id = json_get_string(obj, "id");
    seg.text = json_get_string(obj, "text");
    if (!seg.id.empty()) out.push_back(std::move(seg));
  }
  return out;
}

std::vector<JsonSegmentSpan> json_get_segment_spans(const std::string& json, const std::string& key) {
  auto parse_int_field = [](const std::string& obj, const std::string& field, int fallback) {
    const std::string needle = "\"" + field + "\"";
    auto p = obj.find(needle);
    if (p == std::string::npos) return fallback;
    p = obj.find(':', p + needle.size());
    if (p == std::string::npos) return fallback;
    p += 1;
    while (p < obj.size() && std::isspace(static_cast<unsigned char>(obj[p]))) p++;
    size_t e = p;
    while (e < obj.size() && (std::isdigit(static_cast<unsigned char>(obj[e])) || obj[e] == '-')) e++;
    if (e == p) return fallback;
    try {
      return std::stoi(obj.substr(p, e - p));
    } catch (...) {
      return fallback;
    }
  };

  std::vector<JsonSegmentSpan> out;
  const std::string needle = "\"" + key + "\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return out;
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) return out;
  pos = json.find('[', pos);
  if (pos == std::string::npos) return out;
  size_t i = pos + 1;
  while (i < json.size()) {
    while (i < json.size() && std::isspace(static_cast<unsigned char>(json[i]))) i++;
    if (i >= json.size() || json[i] == ']') break;
    if (json[i] == ',') {
      i++;
      continue;
    }
    if (json[i] != '{') {
      i++;
      continue;
    }
    int depth = 0;
    size_t start = i;
    while (i < json.size()) {
      if (json[i] == '{') depth++;
      else if (json[i] == '}') {
        depth--;
        if (depth == 0) {
          i++;
          break;
        }
      }
      i++;
    }
    const std::string obj = json.substr(start, i - start);
    JsonSegmentSpan span;
    span.id = json_get_string(obj, "id");
    span.start = parse_int_field(obj, "start", -1);
    span.end = parse_int_field(obj, "end", -1);
    if (!span.id.empty() && span.start >= 0 && span.end >= span.start) out.push_back(std::move(span));
  }
  return out;
}

std::vector<OverlayRenderedSpan> to_rendered_spans(const std::vector<JsonSegmentSpan>& spans) {
  std::vector<OverlayRenderedSpan> out;
  out.reserve(spans.size());
  for (const auto& s : spans) {
    if (s.start < 0 || s.end < s.start || s.id.empty()) continue;
    out.push_back(OverlayRenderedSpan{
        static_cast<size_t>(s.start), static_cast<size_t>(s.end), s.id});
  }
  return out;
}

std::vector<OverlayRenderedSpan> compute_rendered_spans(
    const std::string& rendered_text,
    const std::vector<std::string>& segment_ids,
    const std::vector<std::string>& segment_texts) {
  std::vector<OverlayRenderedSpan> spans;
  if (segment_ids.empty() || segment_ids.size() != segment_texts.size() || rendered_text.empty()) return spans;

  size_t cursor = 0;
  for (size_t i = 0; i < segment_ids.size(); ++i) {
    const auto& seg_id = segment_ids[i];
    const auto& seg_text = segment_texts[i];
    if (seg_id.empty() || seg_text.empty()) continue;
    size_t target = 0;
    for (unsigned char c : seg_text) {
      if (!std::isspace(c)) target++;
    }
    if (target == 0) continue;
    while (cursor < rendered_text.size() && std::isspace(static_cast<unsigned char>(rendered_text[cursor]))) {
      cursor++;
    }
    if (cursor >= rendered_text.size()) break;
    const size_t start = cursor;
    size_t consumed = 0;
    while (cursor < rendered_text.size() && consumed < target) {
      if (!std::isspace(static_cast<unsigned char>(rendered_text[cursor]))) consumed++;
      cursor++;
    }
    const size_t end = cursor;
    if (end > start) {
      spans.push_back(OverlayRenderedSpan{start, end, seg_id});
    }
  }
  return spans;
}

int json_get_int(const std::string& json, const std::string& key, int fallback) {
  const std::string needle = "\"" + key + "\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return fallback;
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) return fallback;
  pos += 1;
  while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) pos++;
  size_t end = pos;
  while (end < json.size() && (std::isdigit(static_cast<unsigned char>(json[end])) || json[end] == '-')) end++;
  if (end == pos) return fallback;
  try {
    return std::stoi(json.substr(pos, end - pos));
  } catch (...) {
    return fallback;
  }
}

int json_get_int_loose(const std::string& json, const std::string& key, int fallback) {
  const int direct = json_get_int(json, key, fallback);
  if (direct != fallback) return direct;
  const std::string as_string = json_get_string(json, key);
  const double parsed = parse_loose_number(as_string, static_cast<double>(fallback));
  if (parsed == static_cast<double>(fallback)) return fallback;
  return static_cast<int>(std::lround(parsed));
}

double json_get_double_loose(const std::string& json, const std::string& key, double fallback) {
  const std::string as_string = json_get_string(json, key);
  if (!as_string.empty()) {
    return parse_loose_number(as_string, fallback);
  }
  const int as_int = json_get_int(json, key, std::numeric_limits<int>::min());
  if (as_int != std::numeric_limits<int>::min()) return static_cast<double>(as_int);
  return fallback;
}

}  // namespace what_overlay::pipeline
