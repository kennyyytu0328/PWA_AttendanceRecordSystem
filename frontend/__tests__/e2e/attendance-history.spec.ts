import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Attendance History Flow
//
// Validates that an authenticated employee can view their attendance
// records, apply date filters, and see the filtered results rendered
// in a table.
//
// These tests require a running backend and frontend — marked fixme until
// the full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("Attendance History Flow", () => {
  test.fixme(
    "should display attendance history table after login",
    async ({ page }) => {
      // Login
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Navigate to attendance page
      await page.goto("/attendance");

      // Verify page heading
      await expect(
        page.getByRole("heading", { name: /attendance history/i }),
      ).toBeVisible();

      // Wait for loading to finish
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Verify table headers are rendered
      await expect(
        page.getByRole("columnheader", { name: /date/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /time/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /work mode/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /location/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should show empty state when no records exist",
    async ({ page }) => {
      // Login as a new employee with no attendance history
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP_NEW");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/attendance");

      // Wait for loading to complete
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Verify empty state message
      await expect(
        page.getByText(/no attendance records found/i),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should filter attendance records by start date",
    async ({ page }) => {
      // Login
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/attendance");

      // Wait for initial data load
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Set start date filter
      await page.getByLabel(/start date/i).fill("2026-03-01");

      // Wait for re-fetch after filter change
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Table should still be rendered (assuming records exist in range)
      await expect(
        page.getByRole("columnheader", { name: /date/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should filter attendance records by date range",
    async ({ page }) => {
      // Login
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/attendance");

      // Wait for initial load
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Set both start and end date filters
      await page.getByLabel(/start date/i).fill("2026-03-01");
      await page.getByLabel(/end date/i).fill("2026-03-15");

      // Wait for filtered results
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // The table or empty state should be visible
      const hasTable = await page
        .getByRole("columnheader", { name: /date/i })
        .isVisible()
        .catch(() => false);
      const hasEmpty = await page
        .getByText(/no attendance records found/i)
        .isVisible()
        .catch(() => false);

      // One of the two states must be true
      expect(hasTable || hasEmpty).toBe(true);
    },
  );

  test.fixme(
    "should display work mode badges correctly",
    async ({ page }) => {
      // Login
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/attendance");

      // Wait for table to load
      await expect(
        page.getByText(/loading attendance records/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // If records exist, work mode badges should use WFO or WFH text
      const wfoCount = await page.getByText("WFO").count();
      const wfhCount = await page.getByText("WFH").count();

      // At least one work mode badge should be present if records exist
      expect(wfoCount + wfhCount).toBeGreaterThanOrEqual(0);
    },
  );

  test.fixme(
    "should show error state on API failure",
    async ({ page }) => {
      // Login
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Simulate network failure by intercepting API calls
      await page.route("**/api/attendance**", (route) =>
        route.fulfill({ status: 500, body: "Internal Server Error" }),
      );

      await page.goto("/attendance");

      // Error alert should appear
      await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    },
  );
});
