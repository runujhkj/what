#include "what_overlay/pipeline/body_text_fit_inputs.h"

#include <cassert>
#include <string>

using what_overlay::pipeline::limit_tail_lines_for_fit;
using what_overlay::pipeline::normalize_soft_breaks_for_fit;

int main() {
  {
    const std::string out = normalize_soft_breaks_for_fit("alpha   beta\r\n\n gamma");
    assert(out == "alpha beta\ngamma");
  }

  {
    const std::string out = normalize_soft_breaks_for_fit("line1\nline2\nline3");
    assert(out == "line1\nline2\nline3");
  }

  {
    const std::string out = limit_tail_lines_for_fit("a\nb\nc\nd", 2);
    assert(out == "c\nd");
  }

  {
    const std::string out = limit_tail_lines_for_fit("a\nb", 5);
    assert(out == "a\nb");
  }

  return 0;
}
