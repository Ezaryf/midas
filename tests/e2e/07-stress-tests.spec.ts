import { test, expect } from '@playwright/test';

test.describe('Stress Tests - Aggressive Testing', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should handle 10 rapid signal generations', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 10; i++) {
      await generateBtn.click();
      await page.waitForTimeout(500);
    }
    
    // Should still be functional
    await expect(page.getByText('Midas')).toBeVisible();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
  });

  test('should handle rapid timeframe switching', async ({ page }) => {
    const timeframes = ['M1', 'M3', 'M5', 'M15', 'H1', 'H4'];
    
    for (let i = 0; i < 20; i++) {
      const tf = timeframes[i % timeframes.length];
      await page.getByText(tf).click();
      await page.waitForTimeout(100);
    }
    
    // Chart should still be visible
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('should handle rapid style switching with signal generation', async ({ page }) => {
    const styles = ['Scalper', 'Intraday', 'Swing'];
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 6; i++) {
      const style = styles[i % styles.length];
      await page.getByText(style).click();
      await generateBtn.click();
      await page.waitForTimeout(1000);
    }
    
    // Should still work
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle rapid panel toggling', async ({ page }) => {
    const leftToggle = page.locator('button').filter({ has: page.locator('svg') }).first();
    const rightToggle = page.locator('button').filter({ has: page.locator('svg') }).last();
    
    for (let i = 0; i < 20; i++) {
      await leftToggle.click();
      await page.waitForTimeout(50);
      await rightToggle.click();
      await page.waitForTimeout(50);
    }
    
    // Should still be functional
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle long session without memory leaks', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    // Generate 20 signals over time
    for (let i = 0; i < 20; i++) {
      await generateBtn.click();
      await page.waitForTimeout(2000);
      
      // Verify page is still responsive
      await expect(page.getByText('Midas')).toBeVisible();
    }
  });

  test('should handle network interruption simulation', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Simulate offline
    await page.context().setOffline(true);
    await page.waitForTimeout(2000);
    
    // Try to generate (should fail gracefully)
    await generateBtn.click();
    await page.waitForTimeout(3000);
    
    // Go back online
    await page.context().setOffline(false);
    await page.waitForTimeout(2000);
    
    // Should recover
    await generateBtn.click();
    await page.waitForTimeout(5000);
  });

  test('should handle extreme viewport sizes', async ({ page }) => {
    // Very small
    await page.setViewportSize({ width: 800, height: 600 });
    await page.waitForTimeout(1000);
    await expect(page.getByText('Midas')).toBeVisible();
    
    // Very large
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.waitForTimeout(1000);
    await expect(page.getByText('Midas')).toBeVisible();
    
    // Ultra-wide
    await page.setViewportSize({ width: 3440, height: 1440 });
    await page.waitForTimeout(1000);
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle concurrent user actions', async ({ page }) => {
    // Perform multiple actions simultaneously
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    await Promise.all([
      generateBtn.click(),
      page.getByText('M5').click(),
      page.getByText('Intraday').click(),
    ]);
    
    await page.waitForTimeout(5000);
    
    // Should still be functional
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle chart zoom extremes', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await canvas.waitFor({ state: 'visible' });
    
    // Extreme zoom in
    await canvas.hover();
    for (let i = 0; i < 10; i++) {
      await page.mouse.wheel(0, -100);
      await page.waitForTimeout(100);
    }
    
    // Extreme zoom out
    for (let i = 0; i < 10; i++) {
      await page.mouse.wheel(0, 100);
      await page.waitForTimeout(100);
    }
    
    // Chart should still be functional
    await expect(canvas).toBeVisible();
  });

  test('should handle rapid execute button clicks', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Rapidly click execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    for (let i = 0; i < 5; i++) {
      if (await executeBtn.isEnabled()) {
        await executeBtn.click();
      }
      await page.waitForTimeout(200);
    }
    
    // Should handle gracefully
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle browser back/forward navigation', async ({ page }) => {
    // Navigate to settings
    await page.getByRole('link', { name: /settings/i }).click();
    await page.waitForTimeout(1000);
    
    // Go back
    await page.goBack();
    await page.waitForTimeout(1000);
    
    // Should be back on dashboard
    await expect(page.getByText('Midas')).toBeVisible();
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
    
    // Go forward
    await page.goForward();
    await page.waitForTimeout(1000);
    
    // Go back again
    await page.goBack();
    await page.waitForTimeout(1000);
  });

  test('should handle page refresh during signal generation', async ({ page }) => {
    // Start generating
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await page.waitForTimeout(2000);
    
    // Refresh page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Should recover
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle multiple tabs/windows', async ({ context }) => {
    // Open second tab
    const page2 = await context.newPage();
    await page2.goto('/dashboard');
    await page2.waitForLoadState('networkidle');
    
    // Both should work independently
    await expect(page2.getByText('Midas')).toBeVisible();
    
    await page2.close();
  });
});
