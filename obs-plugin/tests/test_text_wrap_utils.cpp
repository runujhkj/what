#include "what_overlay/layout/text_wrap_utils.h"

#include <cassert>
#include <string>
#include <vector>

using what_overlay::layout::join_lines_all;
using what_overlay::layout::join_lines_from;
using what_overlay::layout::limit_tail_lines;
using what_overlay::layout::split_lines;

int main() {
  {
    const auto lines = split_lines("a\nb\nc");
    assert((lines == std::vector<std::string>{"a", "b", "c"}));
  }
  {
    const auto lines = split_lines("a\n");
    assert((lines == std::vector<std::string>{"a", ""}));
  }
  {
    const std::vector<std::string> lines{"x", "y", "z"};
    assert(join_lines_all(lines) == "x\ny\nz");
    assert(join_lines_from(lines, 1) == "y\nz");
  }
  {
    assert(limit_tail_lines("a\nb\nc\nd", 2) == "c\nd");
    assert(limit_tail_lines("a\nb", 5) == "a\nb");
    assert(limit_tail_lines("alpha", 0) == "alpha");
  }
  return 0;
}
