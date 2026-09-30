#include "what_overlay/pipeline/control_http_client.h"

#include <cassert>
#include <string>

using what_overlay::pipeline::HttpUrlParts;
using what_overlay::pipeline::TestStreamToggleRequest;
using what_overlay::pipeline::get_publish_delay_readback;
using what_overlay::pipeline::parse_http_url;
using what_overlay::pipeline::post_publish_delay;
using what_overlay::pipeline::post_test_stream_toggle;

int main() {
  {
    const HttpUrlParts p = parse_http_url("http://127.0.0.1:8780/control/status");
    assert(p.ok);
    assert(p.host == "127.0.0.1");
    assert(p.port == 8780);
    assert(p.path == "/control/status");
  }

  {
    const HttpUrlParts p = parse_http_url("127.0.0.1");
    assert(p.ok);
    assert(p.host == "127.0.0.1");
    assert(p.port == 80);
    assert(p.path == "/");
  }

  {
    const HttpUrlParts p = parse_http_url("http://127.0.0.1:notaport/test");
    assert(!p.ok);
  }

  // Invalid URL paths should fail fast and avoid network assumptions.
  {
    assert(!post_publish_delay("http://:bad", 3));
    assert(get_publish_delay_readback("http://:bad") == -1);
    assert(!post_test_stream_toggle("http://:bad?box=mic", TestStreamToggleRequest{
      true, 3, 280, 3, 640, 6, 3.0
    }));
  }

  return 0;
}
