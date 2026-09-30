#include "what_overlay/render/color_font_utils.h"

namespace what_overlay::render {

uint32_t parse_color_rgba(const std::string& hex) {
  if (hex.empty()) return 0xFFFFFFFF;
  std::string value = hex;
  if (value[0] == '#') value.erase(0, 1);
  if (value.size() != 6 && value.size() != 8) return 0xFFFFFFFF;

  uint32_t raw = 0;
  try {
    raw = static_cast<uint32_t>(std::stoul(value, nullptr, 16));
  } catch (...) {
    return 0xFFFFFFFF;
  }

  uint8_t a = 0xFF;
  uint8_t r = 0;
  uint8_t g = 0;
  uint8_t b = 0;
  if (value.size() == 6) {
    r = static_cast<uint8_t>((raw >> 16) & 0xFF);
    g = static_cast<uint8_t>((raw >> 8) & 0xFF);
    b = static_cast<uint8_t>(raw & 0xFF);
  } else {
    a = static_cast<uint8_t>((raw >> 24) & 0xFF);
    r = static_cast<uint8_t>((raw >> 16) & 0xFF);
    g = static_cast<uint8_t>((raw >> 8) & 0xFF);
    b = static_cast<uint8_t>(raw & 0xFF);
  }
  return (static_cast<uint32_t>(a) << 24) |
         (static_cast<uint32_t>(r) << 16) |
         (static_cast<uint32_t>(g) << 8) |
         static_cast<uint32_t>(b);
}

uint32_t argb_to_abgr(uint32_t argb) {
  const uint8_t a = static_cast<uint8_t>((argb >> 24) & 0xFF);
  const uint8_t r = static_cast<uint8_t>((argb >> 16) & 0xFF);
  const uint8_t g = static_cast<uint8_t>((argb >> 8) & 0xFF);
  const uint8_t b = static_cast<uint8_t>(argb & 0xFF);
  return (static_cast<uint32_t>(a) << 24) |
         (static_cast<uint32_t>(b) << 16) |
         (static_cast<uint32_t>(g) << 8) |
         static_cast<uint32_t>(r);
}

uint32_t parse_text_color_for_obs(const std::string& hex) {
  return argb_to_abgr(parse_color_rgba(hex));
}

uint32_t parse_bg_color_for_render(const std::string& hex) {
  return argb_to_abgr(parse_color_rgba(hex));
}

}  // namespace what_overlay::render
