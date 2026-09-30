#pragma once

#include "what_overlay/overlay_state.h"

#include <string>
#include <vector>

namespace what_overlay::pipeline {

struct JsonSegment {
  std::string id;
  std::string text;
};

struct JsonSegmentSpan {
  std::string id;
  int start = -1;
  int end = -1;
};

std::string json_get_string(const std::string& json, const std::string& key);
bool json_has_key(const std::string& json, const std::string& key);
std::vector<std::string> json_get_string_array(const std::string& json, const std::string& key);
std::vector<JsonSegment> json_get_segments(const std::string& json, const std::string& key);
std::vector<JsonSegmentSpan> json_get_segment_spans(const std::string& json, const std::string& key);
std::vector<OverlayRenderedSpan> to_rendered_spans(const std::vector<JsonSegmentSpan>& spans);
std::vector<OverlayRenderedSpan> compute_rendered_spans(
    const std::string& rendered_text,
    const std::vector<std::string>& segment_ids,
    const std::vector<std::string>& segment_texts);
int json_get_int(const std::string& json, const std::string& key, int fallback = -1);
int json_get_int_loose(const std::string& json, const std::string& key, int fallback = -1);
double json_get_double_loose(const std::string& json, const std::string& key, double fallback = -1.0);

}  // namespace what_overlay::pipeline
