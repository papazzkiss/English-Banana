import type { CapacitorConfig } from "@capacitor/cli";
import { readFileSync } from "node:fs";

/** Android app (Capacitor). The app is the deployed Banana English web app in a WebView:
 * the Next.js server proxies /api to FastAPI and keeps the httpOnly session cookie first-party,
 * so every feature (sign-in, AI Monkey, microphone, voice) works exactly as on the web.
 *
 * `webDir` is a small launcher (mobile/): it opens the server URL given at build time
 * (BANANA_APP_URL, written to mobile/config.js by scripts/android-config.mjs) and lets the
 * learner enter a new one if it changes (a Cloudflare quick tunnel gets a new URL on restart).
 *
 *   BANANA_APP_URL=https://….trycloudflare.com npm run android:build
 */
function configuredUrl(): string {
  if (process.env.BANANA_APP_URL) return process.env.BANANA_APP_URL;
  try { // written by scripts/android-config.mjs
    return readFileSync("mobile/config.js", "utf8").match(/BANANA_APP_URL = "([^"]*)"/)?.[1] ?? "";
  } catch {
    return "";
  }
}
const appUrl = configuredUrl();

// Pages the WebView may open itself; any other link opens in the system browser.
const allowNavigation = new Set(["*.trycloudflare.com"]);
if (appUrl) allowNavigation.add(new URL(appUrl).hostname);
for (const host of (process.env.BANANA_ALLOW_HOSTS ?? "").split(",")) {
  if (host.trim()) allowNavigation.add(host.trim());
}

const config: CapacitorConfig = {
  appId: "com.bananaenglish.app",
  appName: "Banana English",
  webDir: "mobile",
  server: {
    androidScheme: "https",
    allowNavigation: [...allowNavigation],
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
