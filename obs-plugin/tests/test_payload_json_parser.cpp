#include "what_overlay/pipeline/payload_json_parser.h"

#include <cassert>
#include <string>
#include <vector>

using what_overlay::OverlayRenderedSpan;
using what_overlay::pipeline::JsonSegment;
using what_overlay::pipeline::JsonSegmentSpan;
using what_overlay::pipeline::compute_rendered_spans;
using what_overlay::pipeline::json_get_double_loose;
using what_overlay::pipeline::json_get_int;
using what_overlay::pipeline::json_get_int_loose;
using what_overlay::pipeline::json_get_segment_spans;
using what_overlay::pipeline::json_get_segments;
using what_overlay::pipeline::json_get_string;
using what_overlay::pipeline::json_get_string_array;
using what_overlay::pipeline::json_has_key;
using what_overlay::pipeline::to_rendered_spans;

int main() {
  {
    const std::string payload = R"({"text":"hello","num":5,"arr":["a","b"],"font":"7.05px"})";
    assert(json_get_string(payload, "text") == "hello");
    assert(json_has_key(payload, "num"));
    const auto arr = json_get_string_array(payload, "arr");
    assert(arr.size() == 2);
    assert(arr[0] == "a");
    assert(arr[1] == "b");
    assert(json_get_int(payload, "num", -1) == 5);
    assert(json_get_int_loose(payload, "num", -1) == 5);
    assert(json_get_int_loose(payload, "font", -1) == 7);
    assert(json_get_double_loose(payload, "font", -1.0) > 7.0);
  }

  {
    const std::string payload = R"({
      "segments":[{"id":"s1","text":"test segment 1"},{"id":"s2","text":"test segment 2"}],
      "segmentSpans":[{"id":"s1","start":0,"end":14},{"id":"s2","start":15,"end":29}]
    })";
    const std::vector<JsonSegment> segments = json_get_segments(payload, "segments");
    assert(segments.size() == 2);
    assert(segments[0].id == "s1");
    assert(segments[1].text == "test segment 2");

    const std::vector<JsonSegmentSpan> spans = json_get_segment_spans(payload, "segmentSpans");
    assert(spans.size() == 2);
    const std::vector<OverlayRenderedSpan> rendered = to_rendered_spans(spans);
    assert(rendered.size() == 2);
    assert(rendered[0].segment_id == "s1");
  }

  {
    const std::vector<std::string> ids = {"s1", "s2"};
    const std::vector<std::string> texts = {"test segment 1", "test segment 3"};
    const auto spans = compute_rendered_spans("test segment 1 test segment 3", ids, texts);
    assert(spans.size() == 2);
    assert(spans[0].segment_id == "s1");
    assert(spans[1].segment_id == "s2");
    assert(spans[0].start == 0);
    assert(spans[0].end > spans[0].start);
  }

  return 0;
}
