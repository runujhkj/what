#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

// Minimal TCP client helpers over BSD sockets (macOS/Linux) and Winsock (Windows).
namespace what_overlay::net {

// Opaque socket handle: an fd on POSIX, a SOCKET on Windows. Both fit in intptr_t and
// INVALID_SOCKET maps to -1, which keeps winsock headers out of every includer.
using Handle = std::intptr_t;
constexpr Handle kInvalid = -1;

// Connect to host:port over TCP (IPv4 or IPv6); kInvalid on failure.
Handle connect_tcp(const std::string& host, int port);

// Send all of `data`; returns the byte count, or -1 if the connection failed first.
long send_all(Handle socket, const std::string& data);

// Receive up to `len` bytes; <= 0 on close or error.
long recv_some(Handle socket, char* buf, std::size_t len);

void shutdown_both(Handle socket);
void close_socket(Handle socket);

}  // namespace what_overlay::net
