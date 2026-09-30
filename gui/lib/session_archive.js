"use strict";

// Runs `python -m what session pack|unpack --json` (what/cli/handle_session.py) for the GUI,
// so the .what format has one implementation. Resolves with the command's JSON result; a
// failure resolves as { ok: false, error } rather than rejecting.

function createSessionArchive({ spawn, python, cwd, env = process.env }) {
  function run(args) {
    return new Promise((resolve) => {
      let proc;
      try {
        proc = spawn(python, ["-m", "what", "session", ...args, "--json"], {
          cwd, env, stdio: ["ignore", "pipe", "pipe"],
        });
      } catch (err) {
        resolve({ ok: false, error: `could not start Python: ${err.message || err}` });
        return;
      }
      let stdout = "";
      let stderr = "";
      proc.stdout.on("data", (d) => { stdout += d; });
      proc.stderr.on("data", (d) => { stderr += d; });
      proc.on("error", (err) => resolve({ ok: false, error: `could not start Python: ${err.message || err}` }));
      proc.on("close", (code) => {
        const line = stdout.trim().split("\n").pop() || "";
        try {
          const result = JSON.parse(line);
          if (result && typeof result === "object") {
            resolve(result);
            return;
          }
        } catch (_) {}
        const detail = stderr.trim().split("\n").slice(-3).join("\n");
        resolve({ ok: false, error: `what session ${args[0]} failed (exit ${code})${detail ? `: ${detail}` : ""}` });
      });
    });
  }

  return {
    // Unpack a .what file into <logsDir>/<session_id>/ -> { ok, session_id, session_dir }.
    unpack: (archivePath, logsDir) => run(["unpack", archivePath, "--logs-dir", logsDir]),
    // Refresh transcript.txt and <session_id>.what (optionally copied to copyTo) -> { ok, path }.
    pack: (sessionDir, copyTo) => run(["pack", sessionDir, ...(copyTo ? ["--copy-to", copyTo] : [])]),
  };
}

module.exports = { createSessionArchive };
