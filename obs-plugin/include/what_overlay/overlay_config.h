#pragma once

#include <string>

namespace what_overlay {

struct OverlayConfig {
  std::string url = "http://127.0.0.1:8790/events";
  std::string header = "";
  // Per-source caption-stream filter. Empty = render all streams (legacy behavior); set to
  // an input_source_id ("mic"/"desktop", falls back to matching client_id) so this source
  // renders only that stream -- two sources give independent mic/desktop caption boxes.
  std::string stream = "";
  int max_segments = 3;
  int max_chars = 280;
  int width_px = 640;
  int height_px = 140;
  double font_size_px = 32.0;
  int padding_x_px = 6;
  int padding_y_px = 4;
  std::string text_color = "#ffffff";
  std::string bg_color = "#00000000";
#ifdef __APPLE__
  std::string font_family = "Helvetica";
#else
  std::string font_family = "Arial";
#endif
  std::string align = "left";
  bool uppercase = false;
  bool auto_shrink_to_fit = true;
  bool no_word_split = true;
  std::string line_break_policy = "reflow_all";
  bool test_stream = false;
  std::string layout_engine = "legacy";
  std::string animation_mode = "none";
  bool outline_enabled = true;
  int outline_thickness_px = 3;
  int delay_seconds = 0;
  std::string control_url = "http://127.0.0.1:8780";
};

}  // namespace what_overlay
