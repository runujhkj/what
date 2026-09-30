#include "what_overlay/render/color_font_utils.h"

#include <cassert>
#include <cstdint>

using what_overlay::render::argb_to_abgr;
using what_overlay::render::parse_bg_color_for_render;
using what_overlay::render::parse_color_rgba;
using what_overlay::render::parse_text_color_for_obs;

int main() {
  {
    const uint32_t c = parse_color_rgba("#112233");
    assert(c == 0xFF112233u);
  }
  {
    const uint32_t c = parse_color_rgba("AA112233");
    assert(c == 0xAA112233u);
  }
  {
    const uint32_t c = parse_color_rgba("bad");
    assert(c == 0xFFFFFFFFu);
  }
  {
    const uint32_t c = argb_to_abgr(0xFF112233u);
    assert(c == 0xFF332211u);
  }
  {
    assert(parse_text_color_for_obs("#112233") == 0xFF332211u);
    assert(parse_bg_color_for_render("#445566") == 0xFF665544u);
  }
  return 0;
}
