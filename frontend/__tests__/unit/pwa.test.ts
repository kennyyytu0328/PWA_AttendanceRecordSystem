import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";

describe("PWA Configuration", () => {
  describe("manifest.json", () => {
    it("has required PWA fields", () => {
      const manifestPath = path.resolve(__dirname, "../../public/manifest.json");
      const manifestRaw = fs.readFileSync(manifestPath, "utf-8");
      const manifest = JSON.parse(manifestRaw);

      expect(manifest.name).toBe("GoGoFresh Attendance");
      expect(manifest.short_name).toBe("Attendance");
      expect(manifest.start_url).toBe("/");
      expect(manifest.display).toBe("standalone");
      expect(manifest.background_color).toBe("#ffffff");
      expect(manifest.theme_color).toBe("#10b981");
      expect(manifest.icons).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            src: "/icons/icon-192.png",
            sizes: "192x192",
            type: "image/png",
          }),
          expect.objectContaining({
            src: "/icons/icon-512.png",
            sizes: "512x512",
            type: "image/png",
          }),
        ])
      );
    });
  });

  describe("isPWAInstalled", () => {
    beforeEach(() => {
      vi.resetModules();
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("returns true in standalone mode", async () => {
      vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));

      const { isPWAInstalled } = await import("@/lib/pwa");
      expect(isPWAInstalled()).toBe(true);
      expect(window.matchMedia).toHaveBeenCalledWith(
        "(display-mode: standalone)"
      );
    });

    it("returns false in browser mode", async () => {
      vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));

      const { isPWAInstalled } = await import("@/lib/pwa");
      expect(isPWAInstalled()).toBe(false);
      expect(window.matchMedia).toHaveBeenCalledWith(
        "(display-mode: standalone)"
      );
    });
  });

  describe("registerServiceWorker", () => {
    beforeEach(() => {
      vi.resetModules();
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("calls navigator.serviceWorker.register with /sw.js", async () => {
      const mockRegister = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal("navigator", {
        ...navigator,
        serviceWorker: { register: mockRegister },
      });

      const { registerServiceWorker } = await import("@/lib/pwa");
      await registerServiceWorker();

      expect(mockRegister).toHaveBeenCalledWith("/sw.js");
    });
  });

  describe("canInstallPWA", () => {
    beforeEach(() => {
      vi.resetModules();
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("returns false by default (no beforeinstallprompt event)", async () => {
      const { canInstallPWA } = await import("@/lib/pwa");
      expect(canInstallPWA()).toBe(false);
    });
  });
});
