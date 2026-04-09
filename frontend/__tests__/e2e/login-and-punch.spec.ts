import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Login and Punch Flow
//
// Validates the core daily workflow: an employee signs in with their
// credentials, lands on the dashboard, then navigates to /punch and
// records an attendance punch.
//
// These tests require a running backend and frontend — marked fixme until
// the full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("Login and Punch Flow", () => {
  test.fixme(
    "should login with valid credentials and redirect to dashboard",
    async ({ page }) => {
      await page.goto("/login");

      // Verify login page renders
      await expect(
        page.getByRole("heading", { name: /gogofresh attendance/i }),
      ).toBeVisible();
      await expect(page.getByText(/sign in to your account/i)).toBeVisible();

      // Fill in credentials
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");

      // Submit the form
      await page.getByRole("button", { name: /sign in/i }).click();

      // Wait for redirect to dashboard (login redirects to "/")
      await page.waitForURL("/");

      // Verify dashboard content
      await expect(
        page.getByRole("heading", { name: /dashboard/i }),
      ).toBeVisible();
      await expect(page.getByText(/welcome/i)).toBeVisible();
    },
  );

  test.fixme(
    "should show an error for invalid credentials",
    async ({ page }) => {
      await page.goto("/login");

      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("wrong-password");
      await page.getByRole("button", { name: /sign in/i }).click();

      // Error alert should appear without navigation
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(/failed|invalid/i);

      // Should remain on login page
      expect(page.url()).toContain("/login");
    },
  );

  test.fixme(
    "should show validation error for empty fields",
    async ({ page }) => {
      await page.goto("/login");

      // Attempt to submit without filling in fields
      await page.getByRole("button", { name: /sign in/i }).click();

      // Browser native validation or Zod validation should prevent submission
      // The form uses HTML `required` attributes, so the browser should block
      const empIdInput = page.getByLabel(/employee id/i);
      await expect(empIdInput).toHaveAttribute("required", "");
    },
  );

  test.fixme(
    "should navigate to punch page and record a punch",
    async ({ page }) => {
      // Login first
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      // Navigate to punch page
      await page.goto("/punch");

      // Verify punch page renders
      await expect(
        page.getByRole("heading", { name: /attendance punch/i }),
      ).toBeVisible();

      // Click the punch button
      await page.getByRole("button", { name: /punch/i }).click();

      // Wait for the punch result to appear
      await expect(page.getByText(/punch recorded/i)).toBeVisible({
        timeout: 10_000,
      });

      // Verify result details are displayed
      await expect(page.getByText(/work mode/i)).toBeVisible();
      await expect(page.getByText(/distance/i)).toBeVisible();
    },
  );

  test.fixme(
    "should redirect unauthenticated user from punch to login",
    async ({ page }) => {
      // Go directly to punch without logging in
      await page.goto("/punch");

      // Should redirect to login
      await page.waitForURL(/\/login/);
      await expect(
        page.getByRole("heading", { name: /gogofresh attendance/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    "should disable punch button while processing",
    async ({ page }) => {
      // Login first
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/punch");

      // Click punch
      const punchButton = page.getByRole("button", { name: /punch/i });
      await punchButton.click();

      // Button should be disabled while processing
      await expect(punchButton).toBeDisabled();
    },
  );
});
