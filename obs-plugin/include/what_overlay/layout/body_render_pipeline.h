#pragma once

#include <string>
#include <vector>

namespace what_overlay::layout {

enum class LineBreakPolicy {
  kReflowAll = 0,
  kBreakOnGapMs = 1,
  kBreakOnSemanticBoundary = 2,
  kPreserveInput = 3,
};

struct BodyRenderOutput {
  std::vector<std::string> lines;
  std::string text;
  bool contains_label_token = false;
};

LineBreakPolicy parse_line_break_policy(const std::string& value);

std::string prepare_body_text_input(const std::string& text,
                                    const std::string& preferred_header,
                                    const std::string& fallback_header,
                                    bool uppercase);

std::string prepare_body_lines_input(const std::vector<std::string>& lines,
                                     const std::string& preferred_header,
                                     const std::string& fallback_header,
                                     bool uppercase,
                                     LineBreakPolicy policy = LineBreakPolicy::kReflowAll);

BodyRenderOutput finalize_body_visible_text(const std::string& visible_text,
                                            const std::string& preferred_header,
                                            const std::string& fallback_header);

// Legacy helpers retained as wrappers for compatibility with existing call sites/tests.
std::string preprocess_body_text(const std::string& text,
                                 const std::string& preferred_header,
                                 const std::string& fallback_header);
std::vector<std::string> preprocess_body_lines(const std::vector<std::string>& lines,
                                               const std::string& preferred_header,
                                               const std::string& fallback_header);
BodyRenderOutput postprocess_visible_text(const std::string& visible_text,
                                          const std::string& preferred_header,
                                          const std::string& fallback_header);

}  // namespace what_overlay::layout
