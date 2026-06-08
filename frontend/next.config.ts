import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // NOTE: `output: "standalone"` is only needed for Docker/self-hosted builds.
  // It is intentionally disabled here for Vercel compatibility.
  // Re-enable it if deploying via Docker Compose or Railway with Dockerfile.
};

export default nextConfig;
