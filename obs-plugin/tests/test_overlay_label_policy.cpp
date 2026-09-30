#include "what_overlay/layout/overlay_label_policy.h"

#include <cassert>
#include <set>
#include <string>
#include <vector>

using what_overlay::layout::canonical_label_set;
using what_overlay::layout::is_label_only_line;
using what_overlay::layout::normalize_label_token;
using what_overlay::layout::resolve_effective_header;
using what_overlay::layout::select_active_header;
using what_overlay::layout::sanitize_body_lines;
using what_overlay::layout::strip_leading_label;

int main() {
  {
    assert(normalize_label_token(" Mic: ") == "mic");
    assert(normalize_label_token("Desktop") == "desktop");
    assert(normalize_label_token("") == "");
  }

  {
    assert(resolve_effective_header("Payload", "Configured", "Current") == "Payload");
    assert(resolve_effective_header("  ", "Configured", "Current") == "Configured");
    assert(resolve_effective_header("", "", "Current") == "Current");
  }

  {
    assert(select_active_header("Configured", "Current") == "Configured");
    assert(select_active_header(" ", "Current") == "Current");
    assert(select_active_header("", "  ") == "");
  }

  {
    const std::set<std::string> labels = canonical_label_set({"Mic", "Desktop"});
    assert(is_label_only_line("Mic", labels));
    assert(is_label_only_line("desktop:", labels));
    assert(!is_label_only_line("desktoping", labels));
  }

  {
    const std::set<std::string> labels = canonical_label_set({"Mic", "Desktop"});
    assert(strip_leading_label("Mic: hello", labels) == "hello");
    assert(strip_leading_label("Desktop - world", labels) == "world");
    assert(strip_leading_label("desktop hello", labels) == "hello");
    assert(strip_leading_label("NoLabel text", labels) == "NoLabel text");
    assert(strip_leading_label("desktoping survives", labels) == "desktoping survives");
  }

  {
    const std::vector<std::string> out = sanitize_body_lines(
        {"Mic", "Desktop", "Desktop: one", "desktop two", "Mic | three", "plain", "desktoping survives"},
        {"Mic", "Desktop"});
    assert((out == std::vector<std::string>{"one", "two", "three", "plain", "desktoping survives"}));
  }

  // Fixture-style integration case mirroring overlay apply semantics:
  // 1) resolve header precedence
  // 2) strip leading header-only line
  // 3) sanitize remaining body lines
  {
    const std::string payload_header = "Desktop";
    const std::string configured_header = "Mic";
    const std::string current_header = "Current";
    const std::string effective = resolve_effective_header(payload_header, configured_header, current_header);
    assert(effective == "Desktop");

    std::vector<std::string> payload_lines{
      "Desktop",
      "Desktop hello world",
      "Desktop: one two",
      "desktoping survives"
    };
    if (!payload_lines.empty() && normalize_label_token(payload_lines.front()) == normalize_label_token(effective)) {
      payload_lines.erase(payload_lines.begin());
    }
    const auto out = sanitize_body_lines(payload_lines, {effective, configured_header});
    assert((out == std::vector<std::string>{"hello world", "one two", "desktoping survives"}));
  }

  // Toggle-cycle fixture: successive payloads switch source/header and must
  // keep label tokens out of body lines each time.
  {
    const std::string configured_header = "";
    std::string current_header = "";

    struct Step {
      std::string payload_header;
      std::vector<std::string> payload_lines;
      std::vector<std::string> want_lines;
    };
    const std::vector<Step> steps{
      {"Mic", {"Mic", "Mic hello", "Mic: one"}, {"hello", "one"}},
      {"Desktop", {"Desktop", "Desktop world", "Desktop - two"}, {"world", "two"}},
      {"Mic", {"Mic", "Mic three", "mic four"}, {"three", "four"}},
      {"Desktop", {"Desktop", "desktop five", "desktoping survives"}, {"five", "desktoping survives"}},
    };

    for (const auto& step : steps) {
      const std::string effective = resolve_effective_header(step.payload_header, configured_header, current_header);
      std::vector<std::string> lines = step.payload_lines;
      if (!lines.empty() && normalize_label_token(lines.front()) == normalize_label_token(effective)) {
        lines.erase(lines.begin());
      }
      const auto out = sanitize_body_lines(lines, {effective, configured_header});
      assert(out == step.want_lines);
      for (const auto& line : out) {
        const std::string n = normalize_label_token(line);
        assert(n != "mic");
        assert(n != "desktop");
      }
      current_header = effective;
    }
  }

  return 0;
}
