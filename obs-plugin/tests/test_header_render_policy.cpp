#include "what_overlay/layout/header_render_policy.h"

#include <cassert>

using what_overlay::layout::compute_label_font_units;
using what_overlay::layout::compute_label_height_px;
using what_overlay::layout::compute_top_extra_px;

int main() {
  assert(compute_label_font_units(7.05, "") == 0);
  assert(compute_label_height_px(7.05, "") == 0);
  assert(compute_top_extra_px(7.05, "", 3) == 0);

  assert(compute_label_font_units(7.05, "Desktop") == 14);
  assert(compute_label_height_px(7.05, "Desktop") == 18);
  assert(compute_top_extra_px(7.05, "Desktop", 3) == 39);

  assert(compute_label_font_units(17.95, "Mic") == 36);
  assert(compute_label_height_px(17.95, "Mic") == 45);
  assert(compute_top_extra_px(17.95, "Mic", 3) == 66);

  return 0;
}
