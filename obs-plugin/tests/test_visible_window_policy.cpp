#include "what_overlay/layout/visible_window_policy.h"

#include <cassert>
#include <vector>
#include <string>

using what_overlay::layout::compute_max_visible_lines;
using what_overlay::layout::trim_oldest_lines;

int main() {
  {
    const int max_visible = compute_max_visible_lines(7, 270, 42.48);
    assert(max_visible == 6);
  }

  {
    const int max_visible = compute_max_visible_lines(3, 500, 80.28);
    assert(max_visible == 3);
  }

  {
    std::vector<std::string> lines{"l1", "l2", "l3"};
    const auto res = trim_oldest_lines(lines, 3);
    assert(res.overflowed == false);
    assert(res.dropped == 0);
    assert(lines.size() == 3);
    assert(lines[0] == "l1");
    assert(lines[2] == "l3");
  }

  {
    std::vector<std::string> lines{"l1", "l2", "l3", "l4", "l5"};
    const auto res = trim_oldest_lines(lines, 3);
    assert(res.overflowed == true);
    assert(res.dropped == 2);
    assert(lines.size() == 3);
    assert(lines[0] == "l3");
    assert(lines[1] == "l4");
    assert(lines[2] == "l5");
  }

  return 0;
}

