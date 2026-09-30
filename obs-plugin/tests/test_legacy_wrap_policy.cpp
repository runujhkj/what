#include "what_overlay/pipeline/legacy_wrap_policy.h"

#include <cassert>
#include <string>

using what_overlay::pipeline::wrap_text_legacy_allow_split;
using what_overlay::pipeline::wrap_text_legacy_word_boundary;

int main() {
  {
    const std::string out =
        wrap_text_legacy_word_boundary("test segment 1 test segment 3", 140, 5.9, 2.10, 6.0);
    // Word-boundary mode should not split tokens.
    assert(out.find("seg\nment") == std::string::npos);
    assert(out.find('\n') != std::string::npos);
    assert(out.find("test") != std::string::npos);
    assert(out.find("segment") != std::string::npos);
  }

  {
    const std::string out =
        wrap_text_legacy_allow_split("test segment 1 test segment 3", 140, 5.9, 2.10, 6.0);
    // Allow-split mode may split within tokens under narrow widths.
    assert(out.find('\n') != std::string::npos);
  }

  {
    const std::string out =
        wrap_text_legacy_word_boundary("line1\nline2", 640, 5.9, 2.10, 6.0);
    // Explicit line breaks are preserved.
    assert(out == "line1\nline2");
  }

  return 0;
}
