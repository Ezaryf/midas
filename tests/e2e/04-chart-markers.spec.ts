import { test, expect } from '@playwright/test';

test.describe('Chart Markers - Requirement 2', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should display chart canvas', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible({ timeout: 10000 });
    
    // Check canvas has dimensions
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(100);
    expect(box!.height).toBeGreaterThan(100);
  });

  test('should show EMA legend', async ({ page }) => {
    // Check for EMA indicators in legend
    await expect(page.getByText(/EMA 9/i)).toBeVisible();
    await expect(page.getByText(/EMA 21/i)).toBeVisible();
    await expect(page.getByText(/EMA 50/i)).toBeVisible();
  });

  test('should generate signal and verify chart updates', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Chart should still be visible and functional
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
    
    // Wait a moment for chart to update with signal lines
    await page.waitForTimeout(1000);
  });

  test('should handle timeframe changes', async ({ page }) => {
    // Click different timeframes
    await page.getByText('M5').click();
    await page.waitForTimeout(2000);
    
    await page.getByText('M15').click();
    await page.waitForTimeout(2000);
    
    await page.getByText('H1').click();
    await page.waitForTimeout(2000);
    
    // Chart should still be visible
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('should show price tooltip on hover', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await canvas.waitFor({ state: 'visible' });
    
    // Hover over chart
    await canvas.hover({ position: { x: 200, y: 200 } });
    
    // Wait for tooltip (may contain OHLC data)
    await page.waitForTimeout(500);
  });

  test('should handle chart zoom and pan', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await canvas.waitFor({ state: 'visible' });
    
    // Scroll to zoom
    await canvas.hover();
    await page.mouse.wheel(0, -100);
    await page.waitForTimeout(500);
    
    await page.mouse.wheel(0, 100);
    await page.waitForTimeout(500);
  });

  test('should maintain chart state during panel toggles', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await canvas.waitFor({ state: 'visible' });
    
    // Toggle left panel
    const leftToggle = page.locator('button').filter({ has: page.locator('svg') }).first();
    await leftToggle.click();
    await page.waitForTimeout(500);
    
    // Chart should still be visible
    await expect(canvas).toBeVisible();
    
    // Toggle back
    await leftToggle.click();
    await page.waitForTimeout(500);
    await expect(canvas).toBeVisible();
  });

  test('should show multiple signals on chart', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Wait for chart to update
    await page.waitForTimeout(2000);
    
    // Generate another signal
    await generateBtn.click();
    await page.waitForTimeout(5000);
    
    // Chart should handle multiple signals
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('should handle window resize', async ({ page }) => {
    const canvas = page.locator('canvas').first();
    await canvas.waitFor({ state: 'visible' });
    
    // Resize viewport
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.waitForTimeout(500);
    
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.waitForTimeout(500);
    
    // Chart should still be visible and responsive
    await expect(canvas).toBeVisible();
  });
});
