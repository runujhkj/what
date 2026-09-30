#include "what_overlay/pipeline/control_http_client.h"

#include "what_overlay/net_compat.h"
#include "what_overlay/pipeline/payload_json_parser.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <string>

namespace what_overlay::pipeline {

namespace {

std::string parse_box_query_key(const std::string& raw_url) {
  const auto q = raw_url.find('?');
  if (q == std::string::npos) return "";
  const std::string query = raw_url.substr(q + 1);
  const std::string needle = "box=";
  const auto pos = query.find(needle);
  if (pos == std::string::npos) return "";
  auto value = query.substr(pos + needle.size());
  const auto amp = value.find('&');
  if (amp != std::string::npos) value = value.substr(0, amp);
  for (auto& ch : value) ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
  if (!value.empty()) return value;
  return "";
}

}  // namespace

HttpUrlParts parse_http_url(const std::string& url) {
  HttpUrlParts parts;
  std::string work = url;
  const std::string prefix = "http://";
  if (work.rfind(prefix, 0) == 0) {
    work = work.substr(prefix.size());
  }
  const auto slash = work.find('/');
  const std::string host_port = slash == std::string::npos ? work : work.substr(0, slash);
  parts.path = slash == std::string::npos ? "/" : work.substr(slash);
  const auto colon = host_port.find(':');
  if (colon != std::string::npos) {
    parts.host = host_port.substr(0, colon);
    try {
      parts.port = std::stoi(host_port.substr(colon + 1));
    } catch (...) {
      return parts;
    }
  } else {
    parts.host = host_port;
  }
  parts.ok = !parts.host.empty();
  return parts;
}

bool post_publish_delay(const std::string& control_url, int delay_seconds) {
  const HttpUrlParts url = parse_http_url(control_url);
  if (!url.ok) return false;
  const net::Handle fd = net::connect_tcp(url.host, url.port);
  if (fd == net::kInvalid) return false;

  const std::string body =
      "{\"publish_delay_seconds\":" + std::to_string(std::max(0, std::min(90, delay_seconds))) + "}";
  std::string req = "POST /control/publish-delay HTTP/1.1\r\n";
  req += "Host: " + url.host + "\r\n";
  req += "Content-Type: application/json\r\n";
  req += "Content-Length: " + std::to_string(body.size()) + "\r\n";
  req += "Connection: close\r\n\r\n";
  req += body;

  const long sent = net::send_all(fd, req);
  net::close_socket(fd);
  return sent == static_cast<long>(req.size());
}

int get_publish_delay_readback(const std::string& control_url) {
  const HttpUrlParts url = parse_http_url(control_url);
  if (!url.ok) return -1;
  const net::Handle fd = net::connect_tcp(url.host, url.port);
  if (fd == net::kInvalid) return -1;

  std::string req = "GET /control/status HTTP/1.1\r\n";
  req += "Host: " + url.host + "\r\n";
  req += "Connection: close\r\n\r\n";
  if (net::send_all(fd, req) < 0) {
    net::close_socket(fd);
    return -1;
  }

  std::string resp;
  char buf[2048];
  while (true) {
    const long n = net::recv_some(fd, buf, sizeof(buf));
    if (n <= 0) break;
    resp.append(buf, static_cast<size_t>(n));
  }
  net::close_socket(fd);
  const auto split = resp.find("\r\n\r\n");
  if (split == std::string::npos) return -1;
  const std::string body = resp.substr(split + 4);
  return json_get_int(body, "publish_delay_seconds", -1);
}

bool post_test_stream_toggle(const std::string& overlay_url, const TestStreamToggleRequest& request) {
  const HttpUrlParts url = parse_http_url(overlay_url);
  if (!url.ok) return false;
  const net::Handle fd = net::connect_tcp(url.host, url.port);
  if (fd == net::kInvalid) return false;

  const std::string box_key = parse_box_query_key(overlay_url);
  const int safe_lines_limit = std::max(1, std::min(10, request.lines_limit));
  const int safe_max_chars = std::max(20, request.max_chars);
  const int safe_max_segments =
      std::max(1, std::min(40, request.max_segments > 0 ? request.max_segments : safe_lines_limit));
  const int safe_width_px = std::max(100, request.width_px);
  const int safe_padding_px = std::max(0, request.padding_px);
  const double safe_font_ui = std::max(0.1, request.font_ui);

  std::string body = std::string("{\"enabled\":") + (request.enabled ? "true" : "false");
  if (!box_key.empty()) body += ",\"box\":\"" + box_key + "\"";
  body += ",\"linesLimit\":" + std::to_string(safe_lines_limit);
  body += ",\"maxChars\":" + std::to_string(safe_max_chars);
  body += ",\"maxSegments\":" + std::to_string(safe_max_segments);
  body += ",\"widthPx\":" + std::to_string(safe_width_px);
  body += ",\"paddingPx\":" + std::to_string(safe_padding_px);
  body += ",\"fontUi\":" + std::to_string(safe_font_ui);
  body += "}";
  std::string req = "POST /test-stream HTTP/1.1\r\n";
  req += "Host: " + url.host + "\r\n";
  req += "Content-Type: application/json\r\n";
  req += "Content-Length: " + std::to_string(body.size()) + "\r\n";
  req += "Connection: close\r\n\r\n";
  req += body;

  const long sent = net::send_all(fd, req);
  net::close_socket(fd);
  return sent == static_cast<long>(req.size());
}

}  // namespace what_overlay::pipeline
