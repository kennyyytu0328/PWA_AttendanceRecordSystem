import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Monthly Submission Flow
//
// Validates the end-to-end leave-remarks + monthly-submission workflow:
// 1. Employee opens /dashboard/monthly-override.
// 2. Edits leave-type and remark on an abnormal day.
// 3. Clicks "本月送單" — WarningModal opens listing the abnormal days.
// 4. Clicks "繼續送出" — submission is recorded.
// 5. HR logs in, opens /reports, filters by "已送單".
//
// These tests require a running backend + frontend with a seeded month of
// attendance data — marked fixme until the full stack is deployed.
// ---------------------------------------------------------------------------

test.describe("Monthly Submission Flow", () => {
  test.fixme(
    "employee edits leave-type/remark and submits month with warning",
    async ({ page }) => {
      await page.goto("/login");

      await page.getByLabel(/employee id/i).fill("EMP001");
      await page.getByLabel(/password/i).fill("password123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("/");

      await page.goto("/dashboard/monthly-override");
      await expect(
        page.getByRole("heading", { name: /monthly|月份/i }),
      ).toBeVisible();

      const firstLeaveTypeSelect = page
        .getByRole("combobox", { name: /leave type|請假類別/i })
        .first();
      await firstLeaveTypeSelect.selectOption({ index: 1 });

      const firstRemarkInput = page
        .getByPlaceholder(/remark|備註/i)
        .first();
      await firstRemarkInput.fill("Pre-approved sick leave");

      await page.getByRole("button", { name: /save|儲存/i }).click();
      await expect(page.getByRole("alert")).toContainText(/success|成功/i);

      await page.getByRole("button", { name: /submit month|本月送單/i }).click();

      const warningDialog = page.getByRole("dialog");
      await expect(warningDialog).toBeVisible();
      await expect(warningDialog).toContainText(/abnormal|異常/i);

      await warningDialog
        .getByRole("button", { name: /proceed|繼續送出|仍要送出/i })
        .click();

      await expect(page.getByText(/submitted|已送單/i)).toBeVisible();
    },
  );

  test.fixme(
    "back-to-edit button closes warning modal without submitting",
    async ({ page }) => {
      await page.goto("/dashboard/monthly-override");
      await page.getByRole("button", { name: /submit month|本月送單/i }).click();

      const warningDialog = page.getByRole("dialog");
      await warningDialog
        .getByRole("button", { name: /back to edit|返回修改/i })
        .click();

      await expect(warningDialog).not.toBeVisible();
      await expect(page.getByText(/not submitted|未送單/i)).toBeVisible();
    },
  );

  test.fixme(
    "HR filters reports by submitted status",
    async ({ page }) => {
      await page.goto("/login");
      await page.getByLabel(/employee id/i).fill("HR001");
      await page.getByLabel(/password/i).fill("hr_password");
      await page.getByRole("button", { name: /sign in/i }).click();

      await page.goto("/reports");

      await page
        .getByLabel(/submission|送單/i)
        .selectOption({ label: /submitted only|僅顯示已送單/i.toString() });

      await expect(
        page.getByRole("columnheader", { name: /submission|送單狀態/i }),
      ).toBeVisible();

      const firstStatusCell = page
        .getByRole("cell")
        .filter({ hasText: /submitted|已送單/i })
        .first();
      await expect(firstStatusCell).toBeVisible();
    },
  );
});
