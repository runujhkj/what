#include "what_overlay/layout/body_render_pipeline.h"

#include <cassert>
#include <vector>

using what_overlay::layout::BodyRenderOutput;
using what_overlay::layout::finalize_body_visible_text;
using what_overlay::layout::LineBreakPolicy;
using what_overlay::layout::parse_line_break_policy;
using what_overlay::layout::postprocess_visible_text;
using what_overlay::layout::prepare_body_lines_input;
using what_overlay::layout::prepare_body_text_input;
using what_overlay::layout::preprocess_body_lines;
using what_overlay::layout::preprocess_body_text;

int main() {
  {
    const auto out = preprocess_body_lines(
        {"Desktop", "Desktop test segment 1", "test segment 2"},
        "Desktop",
        "Desktop");
    assert((out == std::vector<std::string>{"test segment 1", "test segment 2"}));
  }

  {
    const std::string out = preprocess_body_text(
        "Mic\nMic test segment 1\ntest segment 2",
        "Mic",
        "Mic");
    assert(out == "test segment 1\ntest segment 2");
  }

  {
    const BodyRenderOutput out = postprocess_visible_text(
        "Desktop\ntest segment 10\nMic: test segment 11",
        "Desktop",
        "Mic");
    assert((out.lines == std::vector<std::string>{"test segment 10", "test segment 11"}));
    assert(out.text == "test segment 10\ntest segment 11");
    assert(!out.contains_label_token);
  }

  {
    const BodyRenderOutput out = postprocess_visible_text(
        "desktop",
        "Desktop",
        "Mic");
    assert(out.text.empty());
    assert(out.lines.empty());
    assert(!out.contains_label_token);
  }

  {
    const std::string prepared = prepare_body_text_input(
        "Mic\nMic test segment 1\ntest segment 2",
        "Mic",
        "Mic",
        false);
    const BodyRenderOutput out = finalize_body_visible_text(prepared, "Mic", "Mic");
    assert((out.lines == std::vector<std::string>{"test segment 1", "test segment 2"}));
    assert(out.text == "test segment 1\ntest segment 2");
  }

  {
    const std::string prepared = prepare_body_lines_input(
        {"Desktop", "Desktop test segment 1", "test segment 2"},
        "Desktop",
        "Desktop",
        false);
    const BodyRenderOutput out = finalize_body_visible_text(prepared, "Desktop", "Desktop");
    assert((out.lines == std::vector<std::string>{"test segment 1 test segment 2"}));
    assert(out.text == "test segment 1 test segment 2");
  }

  // Line-break policy seam: text-mode keeps explicit hard breaks, while
  // lines-mode default policy (reflow_all) composes segment boundaries as
  // spaces before wrap.
  {
    const std::string from_text = prepare_body_text_input(
        "Desktop\nDesktop alpha\nbeta",
        "Desktop",
        "Desktop",
        false);
    const std::string from_lines = prepare_body_lines_input(
        {"Desktop", "Desktop alpha", "beta"},
        "Desktop",
        "Desktop",
        false);
    const BodyRenderOutput out_text = finalize_body_visible_text(from_text, "Desktop", "Desktop");
    const BodyRenderOutput out_lines = finalize_body_visible_text(from_lines, "Desktop", "Desktop");
    assert(out_text.text == "alpha\nbeta");
    assert(out_lines.text == "alpha beta");
    assert((out_lines.lines == std::vector<std::string>{"alpha beta"}));
    assert(out_text.lines != out_lines.lines);
  }

  {
    assert(parse_line_break_policy("reflow_all") == LineBreakPolicy::kReflowAll);
    assert(parse_line_break_policy("break_on_gap_ms") == LineBreakPolicy::kBreakOnGapMs);
    assert(parse_line_break_policy("break_on_semantic_boundary") ==
           LineBreakPolicy::kBreakOnSemanticBoundary);
    assert(parse_line_break_policy("unknown_policy") == LineBreakPolicy::kReflowAll);
  }

  return 0;
}
