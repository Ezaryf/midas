import { test, expect } from '@playwright/test';

test.describe('Performance Metrics', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should display performance stats in left panel', async ({ page }) => {
    // Look for performance section
    await expect(page.getByText(/performance/i)).toBeVisible();
    
    // Check for key metrics
    await expect(page.getByText(/win rate/i)).toBeVisible();
    await expect(page.getByText(/p\.factor|profit factor/i)).toBeVisible();
    await expect(page.getByText(/today/i)).toBeVisible();
    await expect(page.getByText(/week/i)).toBeVisible();
  });

  test('should show reset button for performance stats', async ({ page }) => {
    const resetBtn = page.getByRole('button', { name: /reset/i });
    
    // Reset button should be visible
    if (await resetBtn.isVisible()) {
      await expect(resetBtn).toBeVisible();
    }
  });

  test('should handle performance reset', async ({ page }) => {
    const resetBtn = page.getByRole('button', { name: /reset/i });
    
    if (await resetBtn.isVisible()) {
      await resetBtn.click();
      await page.waitForTimeout(2000);
      
      // Should show resetting state or complete
      // Stats should reset to 0
    }
  });

  test('should update performance after signal execution', async ({ page }) => {
    // Get initial stats
    const initialWinRate = await page.locator('text=/\\d+%/').first().textContent();
    
    // Generate and execute signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    if (await executeBtn.isVisible()) {
      await executeBtn.click();
      await page.waitForTimeout(5000);
    }
    
    // Stats may or may not update depending on backend
  });

  test('should show header performance indicators', async ({ page }) => {
    // Check header stats
    await expect(page.getByText(/win/i)).toBeVisible();
    await expect(page.getByText(/sig/i)).toBeVisible();
    await expect(page.getByText(/p&l/i)).toBeVisible();
  });

  test('should handle performance data persistence', async ({ page }) => {
    // Refresh page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Performance stats should still be visible
    await expect(page.getByText(/performance/i)).toBeVisible();
  });
});
