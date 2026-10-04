import nextEnv from "@next/env";
import { fileURLToPath } from "node:url";

// Quick Start keeps shared auth configuration in the repository root.
nextEnv.loadEnvConfig(fileURLToPath(new URL("..", import.meta.url)), process.env.NODE_ENV === "development", console, true);

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  output: "standalone",
  reactStrictMode: true,
  async redirects() {
    // Old auth paths still linked from emails and bookmarks. Query strings carry over.
    return [
      { source: "/login", destination: "/auth/login", permanent: true },
      { source: "/register", destination: "/auth/signup", permanent: true },
      { source: "/auth/signin", destination: "/auth/login", permanent: true },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
      {
        source: "/api/autopilot/approve",
        // Legacy emails carried a token in their URL; never forward it as Referer.
        headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
      },
    ];
  },
};

export default nextConfig;
