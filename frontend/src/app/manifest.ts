import type { MetadataRoute } from "next";

// Base path under which the app is served (e.g. "/gogoffcc-arms" in
// production behind the www.gogoffcc.com upstream proxy). Empty in dev.
// MUST match next.config.ts `basePath`.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "GoGoFresh Attendance",
    short_name: "Attendance",
    start_url: `${basePath}/`,
    scope: `${basePath}/`,
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#10b981",
    icons: [
      {
        src: `${basePath}/icons/icon-192.png`,
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: `${basePath}/icons/icon-512.png`,
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}
