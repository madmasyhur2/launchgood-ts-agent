import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Docker multi-stage builds — produces a self-contained
  // server.js bundle in .next/standalone that doesn't need node_modules.
  output: "standalone",
};

export default nextConfig;
