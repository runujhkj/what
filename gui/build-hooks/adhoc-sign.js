"use strict";

// electron-builder afterPack hook for macOS. Adding resources to the Electron bundle
// breaks its seal, and an Apple-silicon Mac refuses to run a bundle whose signature is
// invalid ("What is damaged"). When no signing certificate is configured, ad-hoc sign the
// whole bundle so it launches; users still get Gatekeeper's unidentified-developer prompt.
// With a real certificate (CSC_LINK / CSC_NAME) electron-builder signs the app itself later,
// so this does nothing.
const { execFileSync } = require("child_process");
const path = require("path");

exports.default = async function adhocSign(context) {
  if (context.electronPlatformName !== "darwin") return;
  if (process.env.CSC_LINK || process.env.CSC_NAME) return;
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  console.log(`  • ad-hoc signing ${app}`);
  execFileSync("codesign", ["--force", "--deep", "--sign", "-", app], { stdio: "inherit" });
};
