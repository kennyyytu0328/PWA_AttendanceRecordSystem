import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Office Location Configuration Flow
//
// Validates that an HR or ADMIN user can view and update the office
// location coordinates from the admin panel.
//
// These tests require a running backend and frontend — marked fixme until
// the full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("Office Location Configuration", () => {
  test.fixme(
    "should display current office location coordinates",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Verify Office Location section heading
      await expect(
        page.getByRole("heading", { name: /office location/i }),
      ).toBeVisible();

      // Wait for location data to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Latitude and longitude inputs should be visible and pre-filled
      const latitudeInput = page.getByLabel(/latitude/i);
      const longitudeInput = page.getByLabel(/longitude/i);

      await expect(latitudeInput).toBeVisible();
      await expect(longitudeInput).toBeVisible();

      // Inputs should have values loaded from the API
      await expect(latitudeInput).not.toHaveValue("");
      await expect(longitudeInput).not.toHaveValue("");
    },
  );

  test.fixme(
    "should update office location with valid coordinates",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Clear and fill new coordinates
      const latitudeInput = page.getByLabel(/latitude/i);
      const longitudeInput = page.getByLabel(/longitude/i);

      await latitudeInput.clear();
      await latitudeInput.fill("25.0330");
      await longitudeInput.clear();
      await longitudeInput.fill("121.5654");

      // Submit the update
      await page
        .getByRole("button", { name: /update location/i })
        .click();

      // Verify success message appears
      await expect(
        page.getByText(/office location updated successfully/i),
      ).toBeVisible({ timeout: 10_000 });
    },
  );

  test.fixme(
    "should persist updated location after page reload",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Update coordinates
      const latitudeInput = page.getByLabel(/latitude/i);
      const longitudeInput = page.getByLabel(/longitude/i);

      await latitudeInput.clear();
      await latitudeInput.fill("13.7563");
      await longitudeInput.clear();
      await longitudeInput.fill("100.5018");

      await page
        .getByRole("button", { name: /update location/i })
        .click();

      // Wait for success
      await expect(
        page.getByText(/office location updated successfully/i),
      ).toBeVisible({ timeout: 10_000 });

      // Reload the page
      await page.reload();

      // Wait for location to load again
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Verify the updated coordinates persisted
      await expect(page.getByLabel(/latitude/i)).toHaveValue("13.7563");
      await expect(page.getByLabel(/longitude/i)).toHaveValue("100.5018");
    },
  );

  test.fixme(
    "should show error for invalid latitude",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Enter an out-of-range latitude
      const latitudeInput = page.getByLabel(/latitude/i);
      await latitudeInput.clear();
      await latitudeInput.fill("999");

      await page
        .getByRole("button", { name: /update location/i })
        .click();

      // Error message should appear
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(
        /latitude must be between/i,
      );
    },
  );

  test.fixme(
    "should show error for invalid longitude",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Enter an out-of-range longitude
      const longitudeInput = page.getByLabel(/longitude/i);
      await longitudeInput.clear();
      await longitudeInput.fill("-999");

      await page
        .getByRole("button", { name: /update location/i })
        .click();

      // Error message should appear
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(
        /longitude must be between/i,
      );
    },
  );

  test.fixme(
    "should show error for non-numeric coordinates",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Enter non-numeric values
      const latitudeInput = page.getByLabel(/latitude/i);
      await latitudeInput.clear();
      await latitudeInput.fill("abc");

      await page
        .getByRole("button", { name: /update location/i })
        .click();

      // Error message should appear
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(
        /valid numbers/i,
      );
    },
  );

  test.fixme(
    "should disable submit button while updating",
    async ({ page }) => {
      // Login as HR
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/admin");

      // Wait for location to load
      await expect(
        page.getByText(/loading location/i),
      ).not.toBeVisible({ timeout: 10_000 });

      // Fill valid coordinates
      const latitudeInput = page.getByLabel(/latitude/i);
      const longitudeInput = page.getByLabel(/longitude/i);
      await latitudeInput.clear();
      await latitudeInput.fill("25.0330");
      await longitudeInput.clear();
      await longitudeInput.fill("121.5654");

      // Click submit
      const submitButton = page.getByRole("button", {
        name: /update location/i,
      });
      await submitButton.click();

      // Button should show "Updating..." and be disabled while submitting
      await expect(
        page.getByRole("button", { name: /updating/i }),
      ).toBeDisabled();
    },
  );
});
