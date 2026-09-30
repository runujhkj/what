#pragma once

#include <string>

namespace what_overlay::pipeline {

struct HttpUrlParts {
  std::string host;
  std::string path;
  int port = 80;
  bool ok = false;
};

struct TestStreamToggleRequest {
  bool enabled = false;
  int lines_limit = 3;
  int max_chars = 280;
  int max_segments = 3;
  int width_px = 640;
  int padding_px = 6;
  double font_ui = 3.0;
};

HttpUrlParts parse_http_url(const std::string& url);
bool post_publish_delay(const std::string& control_url, int delay_seconds);
int get_publish_delay_readback(const std::string& control_url);
bool post_test_stream_toggle(const std::string& overlay_url, const TestStreamToggleRequest& request);

}  // namespace what_overlay::pipeline
