/** API calls and listening audio are proxied to the FastAPI service, so the browser talks to
 * one origin (no CORS, works the same in docker compose and locally). */
const API = process.env.API_INTERNAL_URL || "http://127.0.0.1:8010";

const nextConfig = {
  output: "standalone",
  // Grading runs as background jobs, but the tutor, conversation and AI Monkey replies still
  // wait for the LLM in the request (seconds on a GPU, up to minutes for an 8B model on CPU).
  // The proxy outlasts the API's LLM timeout (build arg LLM_TIMEOUT_SECONDS, like
  // BANANA_LLM_TIMEOUT_SECONDS), so a slow reply ends as the API's 503, not a proxy error.
  // Next's default is 30 s.
  experimental: { proxyTimeout: (Number(process.env.LLM_TIMEOUT_SECONDS) || 180) * 1000 + 30_000 },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/media/:path*", destination: `${API}/media/:path*` },
    ];
  },
};

export default nextConfig;
