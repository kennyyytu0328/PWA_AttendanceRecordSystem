import type { NextConfig } from "next";

// In production this is set to "/gogoffcc-arms" so all routes, static assets,
// and next/link hrefs are emitted under the upstream proxy's path prefix.
// Left empty in dev so http://localhost:3000/login keeps working unchanged.
// Must be set at BUILD time (Next.js inlines it into the client bundle).
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["192.168.*.*"],
  basePath: basePath || undefined,
};

export default nextConfig;
