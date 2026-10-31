import type { NextConfig } from "next";

// Everything the browser needs goes through :3000, so a phone on the hotspot only needs one port
// for REST. The hub WebSocket is reached directly on :8000.
const svc = (name: string, port: number) => process.env[`LEASH_${name}_URL`] ?? `http://127.0.0.1:${port}`;

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      { source: "/api/hub/:path*", destination: `${svc("HUB", 8000)}/:path*` },
      { source: "/api/gateway/:path*", destination: `${svc("GATEWAY", 8001)}/:path*` },
      { source: "/api/rail/:path*", destination: `${svc("RAIL", 8002)}/:path*` },
      { source: "/shop/:path*", destination: `${svc("SHOPS", 8003)}/:path*` },
    ];
  },
};

export default nextConfig;
