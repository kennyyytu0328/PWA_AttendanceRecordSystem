import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// PWA Installability Tests
//
// Validates that the application meets basic Progressive Web App criteria:
// manifest link, theme-color meta tag, and service worker registration.
//
// The manifest and theme-color checks can run against a dev server, but
// service worker registration typically requires HTTPS or localhost with
// proper next-pwa configuration. All tests are marked fixme until the
// full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("PWA Installability", () => {
  test.fixme(
    "should have a manifest link in the document head",
    async ({ page }) => {
      await page.goto("/");

      // The <link rel="manifest"> tag should reference /manifest.json
      const manifestLink = page.locator('link[rel="manifest"]');
      await expect(manifestLink).toHaveCount(1);

      const href = await manifestLink.getAttribute("href");
      expect(href).toBe("/manifest.json");
    },
  );

  test.fixme(
    "should serve a valid manifest.json",
    async ({ page, request }) => {
      // Fetch the manifest directly
      const response = await request.get("/manifest.json");

      expect(response.status()).toBe(200);

      const manifest = await response.json();

      // Required PWA manifest fields
      expect(manifest.name).toBe("GoGoFresh Attendance");
      expect(manifest.short_name).toBe("Attendance");
      expect(manifest.start_url).toBe("/");
      expect(manifest.display).toBe("standalone");
      expect(manifest.theme_color).toBe("#10b981");
      expect(manifest.background_color).toBe("#ffffff");

      // Must have at least one icon
      expect(manifest.icons).toBeDefined();
      expect(manifest.icons.length).toBeGreaterThanOrEqual(1);

      // Verify icon sizes include 192x192 and 512x512
      const sizes = manifest.icons.map(
        (icon: { sizes: string }) => icon.sizes,
      );
      expect(sizes).toContain("192x192");
      expect(sizes).toContain("512x512");
    },
  );

  test.fixme(
    "should have a theme-color meta tag",
    async ({ page }) => {
      await page.goto("/");

      // The <meta name="theme-color"> should be present
      const themeColorMeta = page.locator('meta[name="theme-color"]');
      await expect(themeColorMeta).toHaveCount(1);

      const content = await themeColorMeta.getAttribute("content");
      expect(content).toBe("#10b981");
    },
  );

  test.fixme(
    "should have viewport meta tag for mobile",
    async ({ page }) => {
      await page.goto("/");

      // Verify viewport meta tag is present (standard for PWAs)
      const viewportMeta = page.locator('meta[name="viewport"]');
      await expect(viewportMeta).toHaveCount(1);

      const content = await viewportMeta.getAttribute("content");
      expect(content).toContain("width=device-width");
    },
  );

  test.fixme(
    "should register a service worker",
    async ({ page }) => {
      await page.goto("/");

      // Evaluate service worker registration in the browser context
      const hasServiceWorker = await page.evaluate(async () => {
        if (!("serviceWorker" in navigator)) {
          return false;
        }

        try {
          const registration =
            await navigator.serviceWorker.getRegistration();
          return registration !== undefined;
        } catch {
          return false;
        }
      });

      expect(hasServiceWorker).toBe(true);
    },
  );

  test.fixme(
    "should have correct app title",
    async ({ page }) => {
      await page.goto("/");

      // Verify the page title matches the manifest name
      await expect(page).toHaveTitle(/gogofresh attendance/i);
    },
  );

  test.fixme(
    "should be responsive on mobile viewport",
    async ({ page }) => {
      // Set a mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto("/login");

      // The login form should still be visible and usable
      await expect(
        page.getByRole("heading", { name: /gogofresh attendance/i }),
      ).toBeVisible();
      await expect(page.getByLabel(/employee id/i)).toBeVisible();
      await expect(page.getByLabel(/password/i)).toBeVisible();
      await expect(
        page.getByRole("button", { name: /sign in/i }),
      ).toBeVisible();

      // The form container should not overflow horizontally
      const isOverflowing = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth;
      });
      expect(isOverflowing).toBe(false);
    },
  );
});
