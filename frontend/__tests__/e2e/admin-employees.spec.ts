import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Admin Employee Management Flow
//
// Validates that an HR or ADMIN user can access the admin panel and
// view the employee list. Also verifies that lower-role users are denied
// access.
//
// These tests require a running backend and frontend — marked fixme until
// the full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("Admin Employee Management", () => {
  test.fixme(
    "should display admin panel with employee list for HR user",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Navigate to admin page
      await page.goto("/admin");

      // Verify admin panel heading
      await expect(
        page.getByRole("heading", { name: /admin panel/i }),
      ).toBeVisible();

      // Verify Employee Management section renders
      await expect(
        page.getByRole("heading", { name: /employee management/i }),
      ).toBeVisible();

      // Wait for employees to load
      await expect(
        page.getByText(/loading employees/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Verify employee table headers
      await expect(
        page.getByRole("columnheader", { name: /^id$/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /name/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /department/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /role/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("columnheader", { name: /shift/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should display employee rows with correct data",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for employee table to load
      await expect(
        page.getByText(/loading employees/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Verify at least one employee row exists in the table
      const rows = page.locator("table tbody tr");
      await expect(rows.first()).toBeVisible();

      // Each row should have employee data cells
      const firstRow = rows.first();
      const cells = firstRow.locator("td");
      await expect(cells).toHaveCount(5);
    },
  );

  test.fixme(
    "should show access denied for regular employees",
    async ({ page }) => {
      // Login as regular employee
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Navigate to admin page
      await page.goto("/admin");

      // Should see Access Denied
      await expect(
        page.getByRole("heading", { name: /access denied/i }),
      ).toBeVisible();

      // Should NOT see Employee Management section
      await expect(
        page.getByRole("heading", { name: /employee management/i }),
      ).not.toBeVisible();
    },
  );

  test.fixme(
    "should show Office Location section for HR user",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Verify Office Location section renders
      await expect(
        page.getByRole("heading", { name: /office location/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should show System Config section only for ADMIN users",
    async ({ page }) => {
      // Login as ADMIN
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("ADMIN001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // ADMIN should see all three sections
      await expect(
        page.getByRole("heading", { name: /employee management/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /office location/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /system config/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should NOT show System Config section for HR users",
    async ({ page }) => {
      // Login as HR (not ADMIN)
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // HR should see Employee Management and Office Location
      await expect(
        page.getByRole("heading", { name: /employee management/i }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /office location/i }),
      ).toBeVisible();

      // But NOT System Config
      await expect(
        page.getByRole("heading", { name: /system config/i }),
      ).not.toBeVisible();
    },
  );

  test.fixme(
    "should show error state when employee API fails",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Intercept the employees endpoint to simulate failure
      await page.route("**/api/employees", (route) =>
        route.fulfill({ status: 500, body: "Internal Server Error" }),
      );

      await page.goto("/admin");

      // Error alert should appear in the Employee Management section
      await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    },
  );
});
