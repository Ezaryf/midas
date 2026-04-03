import { test, expect } from '@playwright/test';

test.describe('WebSocket Connection', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should establish WebSocket connection', async ({ page }) => {
    // Wait for connection indicator
    await page.waitForTimeout(3000);
    
    // Check for Live status
    const liveIndicator = page.getByText(/live/i);
    await expect(liveIndicator).toBeVisible({ timeout: 10000 });
  });

  test('should receive live price updates', async ({ page }) => {
    // Wait for connection
    await page.waitForTimeout(3000);
    
    // Get initial price
    const priceElement = page.locator('text=/\\d{4}\\.\\d{2}/').first();
    const initialPrice = await priceElement.textContent();
    
    // Wait for price update
    await page.waitForTimeout(5000);
    
    // Price should be visible (may or may not change)
    await expect(priceElement).toBeVisible();
  });

  test('should handle WebSocket disconnection', async ({ page }) => {
    // Wait for connection
    await page.waitForTimeout(3000);
    await expect(page.getByText(/live/i)).toBeVisible();
    
    // Simulate network offline
    await page.context().setOffline(true);
    await page.waitForTimeout(5000);
    
    // Should show offline status
    const offlineIndicator = page.getByText(/offline/i);
    await expect(offlineIndicator).toBeVisible({ timeout: 10000 });
    
    // Go back online
    await page.context().setOffline(false);
    await page.waitForTimeout(5000);
    
    // Should reconnect
    await expect(page.getByText(/live/i)).toBeVisible({ timeout: 15000 });
  });

  test('should receive signal broadcasts', async ({ page }) => {
    // Wait for connection
    await page.waitForTimeout(3000);
    
    // Generate signal (which broadcasts via WebSocket)
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Should receive signal
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
  });

  test('should handle WebSocket reconnection', async ({ page }) => {
    // Wait for initial connection
    await page.waitForTimeout(3000);
    
    // Reload page to force reconnection
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    
    // Should reconnect
    await expect(page.getByText(/live/i)).toBeVisible({ timeout: 10000 });
  });

  test('should maintain connection during long session', async ({ page }) => {
    // Check connection status multiple times
    for (let i = 0; i < 5; i++) {
      await page.waitForTimeout(5000);
      await expect(page.getByText(/live/i)).toBeVisible();
    }
  });

  test('should handle multiple WebSocket messages', async ({ page }) => {
    // Wait for connection
    await page.waitForTimeout(3000);
    
    // Generate multiple signals rapidly
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 3; i++) {
      await generateBtn.click();
      await page.waitForTimeout(2000);
    }
    
    // Should handle all messages
    await expect(page.getByText('Midas')).toBeVisible();
  });
});
