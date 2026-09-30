#include "what_overlay/net_compat.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace what_overlay::net {

namespace {

#ifdef _WIN32
using Native = SOCKET;

bool ensure_started() {
  // Winsock must be initialised once per process before any socket call.
  static const bool ok = [] {
    WSADATA data;
    return WSAStartup(MAKEWORD(2, 2), &data) == 0;
  }();
  return ok;
}

Native native(Handle h) { return h == kInvalid ? INVALID_SOCKET : static_cast<Native>(h); }
Handle wrap(Native s) { return s == INVALID_SOCKET ? kInvalid : static_cast<Handle>(s); }
void close_native(Native s) { closesocket(s); }
#else
using Native = int;

bool ensure_started() { return true; }
Native native(Handle h) { return static_cast<Native>(h); }
Handle wrap(Native s) { return s < 0 ? kInvalid : static_cast<Handle>(s); }
void close_native(Native s) { ::close(s); }
#endif

}  // namespace

Handle connect_tcp(const std::string& host, int port) {
  if (!ensure_started()) return kInvalid;
  struct addrinfo hints {};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  struct addrinfo* result = nullptr;
  const std::string port_str = std::to_string(port);
  if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &result) != 0) return kInvalid;

  Handle out = kInvalid;
  for (auto* rp = result; rp != nullptr; rp = rp->ai_next) {
    const Native s = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
    if (wrap(s) == kInvalid) continue;
#ifdef _WIN32
    const int rc = connect(s, rp->ai_addr, static_cast<int>(rp->ai_addrlen));
#else
    const int rc = connect(s, rp->ai_addr, rp->ai_addrlen);
#endif
    if (rc == 0) {
      out = wrap(s);
      break;
    }
    close_native(s);
  }
  freeaddrinfo(result);
  return out;
}

long send_all(Handle socket, const std::string& data) {
  std::size_t sent = 0;
  while (sent < data.size()) {
    const std::size_t chunk = data.size() - sent;
#ifdef _WIN32
    const long n = ::send(native(socket), data.data() + sent, static_cast<int>(chunk), 0);
#else
    const long n = static_cast<long>(::send(native(socket), data.data() + sent, chunk, 0));
#endif
    if (n <= 0) return -1;
    sent += static_cast<std::size_t>(n);
  }
  return static_cast<long>(sent);
}

long recv_some(Handle socket, char* buf, std::size_t len) {
#ifdef _WIN32
  return ::recv(native(socket), buf, static_cast<int>(len), 0);
#else
  return static_cast<long>(::recv(native(socket), buf, len, 0));
#endif
}

void shutdown_both(Handle socket) {
#ifdef _WIN32
  ::shutdown(native(socket), SD_BOTH);
#else
  ::shutdown(native(socket), SHUT_RDWR);
#endif
}

void close_socket(Handle socket) {
  if (socket != kInvalid) close_native(native(socket));
}

}  // namespace what_overlay::net
