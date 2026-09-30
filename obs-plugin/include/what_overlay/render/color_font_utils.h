#pragma once

#include <cstdint>
#include <string>

namespace what_overlay::render {

uint32_t parse_color_rgba(const std::string& hex);
uint32_t argb_to_abgr(uint32_t argb);
uint32_t parse_text_color_for_obs(const std::string& hex);
uint32_t parse_bg_color_for_render(const std::string& hex);

}  // namespace what_overlay::render
