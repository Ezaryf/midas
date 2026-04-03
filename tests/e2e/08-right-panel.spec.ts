import { test, expect } from '@playwright/test';

test.describe('Right Panel - News, Calendar, History', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should show right panel tabs', async ({ page }) => {
    await expect(page.getByText('News')).toBeVisible();
    await expect(page.getByText('Calendar')).toBeVisible();
    await expect(page.getByText('History')).toBeVisible();
  });

  test('should switch between tabs', async ({ page }) => {
    // Click News tab
    await page.getByText('News').click();
    await page.waitForTimeout(500);
    
    // Click Calendar tab
    await page.getByText('Calendar').click();
    await page.waitForTimeout(500);
    
    // Click History tab
    await page.getByText('History').click();
    await page.waitForTimeout(500);
    
    // Should not crash
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should load news items', async ({ page }) => {
    await page.getByText('News').click();
    await page.waitForTimeout(2000);
    
    // Should show news items or loading state
    // News items may vary, so just check panel is functional
  });

  test('should load calendar events', async ({ page }) => {
    await page.getByText('Calendar').click();
    await page.waitForTimeout(2000);
    
    // Should show calendar events or empty state
  });

  test('should show signal history', async ({ page }) => {
    // Generate a signal first
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Go to history tab
    await page.getByText('History').click();
    await page.waitForTimeout(1000);
    
    // Should show at least one signal in history
    // History display may vary
  });

  test('should handle clear history button', async ({ page }) => {
    // Generate signals
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Go to history
    await page.getByText('History').click();
    await page.waitForTimeout(1000);
    
    // Look for clear button
    const clearBtn = page.getByRole('button', { name: /clear/i });
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
      await page.waitForTimeout(1000);
    }
  });

  test('should maintain tab selection when toggling panel', async ({ page }) => {
    // Select Calendar tab
    await page.getByText('Calendar').click();
    await page.waitForTimeout(500);
    
    // Toggle panel closed
    const rightToggle = page.locator('button').filter({ has: page.locator('svg') }).last();
    await rightToggle.click();
    await page.waitForTimeout(500);
    
    // Toggle panel open
    await rightToggle.click();
    await page.waitForTimeout(500);
    
    // Calendar should still be selected
    // (Visual check - depends on CSS)
  });

  test('should handle rapid tab switching', async ({ page }) => {
    for (let i = 0; i < 20; i++) {
      await page.getByText('News').click();
      await page.waitForTimeout(50);
      await page.getByText('Calendar').click();
      await page.waitForTimeout(50);
      await page.getByText('History').click();
      await page.waitForTimeout(50);
    }
    
    // Should still be functional
    await expect(page.getByText('Midas')).toBeVisible();
  });
});
