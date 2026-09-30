#include "what_overlay/overlay_client.h"

#include <obs-module.h>

#include <chrono>
#include <cstring>

namespace what_overlay {

namespace {

struct UrlParts {
  std::string host;
  std::string path;
  int port = 80;
  bool ok = false;
};

static UrlParts parse_url(const std::string& url) {
  UrlParts parts;
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
    const std::string port_str = host_port.substr(colon + 1);
    try {
      parts.port = std::stoi(port_str);
    } catch (...) {
      return parts;
    }
  } else {
    parts.host = host_port;
  }
  parts.ok = !parts.host.empty();
  return parts;
}

}  // namespace

void OverlayClient::start() {
  if (running_) return;
  running_ = true;
  worker_ = std::thread([this]() { run(); });
}

void OverlayClient::stop() {
  running_ = false;
  const net::Handle fd = socket_fd_.exchange(net::kInvalid);
  if (fd != net::kInvalid) {
    // Unblocks the worker's recv(); the worker owns closing its own socket.
    net::shutdown_both(fd);
  }
  if (worker_.joinable()) {
    worker_.join();
  }
}

void OverlayClient::run() {
  while (running_) {
    const UrlParts parts = parse_url(url_);
    if (!parts.ok) {
#ifdef what_overlay_debug
      blog(LOG_INFO, "what_overlay: invalid url: %s", url_.c_str());
#endif
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      continue;
    }

    const net::Handle fd = net::connect_tcp(parts.host, parts.port);
    if (fd == net::kInvalid) {
#ifdef what_overlay_debug
      blog(LOG_INFO, "what_overlay: connect failed %s:%d", parts.host.c_str(), parts.port);
#endif
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      continue;
    }

    socket_fd_ = fd;
#ifdef what_overlay_debug
    blog(LOG_INFO, "what_overlay: connected to %s:%d%s", parts.host.c_str(), parts.port, parts.path.c_str());
#endif

    std::string request = "GET " + parts.path + " HTTP/1.1\r\n";
    request += "Host: " + parts.host + "\r\n";
    request += "Accept: text/event-stream\r\n";
    request += "Connection: keep-alive\r\n\r\n";
    net::send_all(fd, request);

    std::string buffer;
    buffer.reserve(4096);
    std::string event_data;
    bool headers_done = false;

    char temp[2048];
    while (running_) {
      const long n = net::recv_some(fd, temp, sizeof(temp) - 1);
      if (n <= 0) break;
      temp[n] = '\0';
      buffer.append(temp, static_cast<std::size_t>(n));

      while (true) {
        const auto pos = buffer.find('\n');
        if (pos == std::string::npos) break;
        std::string line = buffer.substr(0, pos);
        buffer.erase(0, pos + 1);
        if (!line.empty() && line.back() == '\r') line.pop_back();

        if (!headers_done) {
          if (line.empty()) {
            headers_done = true;
          }
          continue;
        }

        if (line.rfind("data:", 0) == 0) {
          std::string payload = line.substr(5);
          if (!payload.empty() && payload[0] == ' ') payload.erase(0, 1);
          if (!event_data.empty()) event_data.push_back('\n');
          event_data += payload;
        } else if (line.empty()) {
          if (!event_data.empty() && on_text_) {
#ifdef what_overlay_debug
            blog(LOG_INFO, "what_overlay: event payload len=%zu", event_data.size());
#endif
            on_text_(event_data);
          }
          event_data.clear();
        }
      }
    }

    socket_fd_.store(net::kInvalid);
    net::close_socket(fd);
#ifdef what_overlay_debug
    blog(LOG_INFO, "what_overlay: disconnected");
#endif
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
  }
}

}  // namespace what_overlay
