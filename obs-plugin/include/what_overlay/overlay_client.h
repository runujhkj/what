#pragma once

#include <functional>
#include <string>
#include <thread>
#include <atomic>

#include "what_overlay/net_compat.h"

namespace what_overlay {

using OverlayTextCallback = std::function<void(const std::string&)>;

// Placeholder for SSE/WebSocket client.
class OverlayClient {
 public:
  OverlayClient() = default;
  ~OverlayClient() = default;

  void set_url(const std::string& url) { url_ = url; }
  void set_on_text(OverlayTextCallback cb) { on_text_ = std::move(cb); }

  // Start receiving overlay updates. Intended to run on a background thread.
  void start();
  // Stop the client and release resources.
  void stop();

 private:
  void run();
  std::string url_;
  OverlayTextCallback on_text_;
  std::atomic<bool> running_{false};
  std::thread worker_;
  // Published by the worker so stop() can shutdown() a blocked recv.
  std::atomic<net::Handle> socket_fd_{net::kInvalid};
};

}  // namespace what_overlay
