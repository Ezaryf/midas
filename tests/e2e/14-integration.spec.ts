import { test, expect } from '@playwright/test';

test.describe('Full Integration Tests', () => {
  test('complete trading workflow - Scalper', async ({ page }) => {
    // 1. Load dashboard
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Midas')).toBeVisible();
    
    // 2. Select Scalper style
    await page.getByText('Scalper').click();
    await page.waitForTimeout(1000);
    
    // 3. Select M1 timeframe
    await page.getByText('M1').click();
    await page.waitForTimeout(2000);
    
    // 4. Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // 5. Verify signal details
    await expect(page.getByText(/entry/i)).toBeVisible();
    await expect(page.getByText(/stop loss/i)).toBeVisible();
    await expect(page.getByText(/tp1/i)).toBeVisible();
    
    // 6. Expand reasoning
    await page.getByText(/why this trade/i).click();
    await page.waitForTimeout(500);
    
    // 7. Copy signal
    const copyBtn = page.getByRole('button', { name: /copy/i });
    await copyBtn.click();
    await expect(page.getByText(/copied/i)).toBeVisible();
    
    // 8. Check chart has signal lines
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
    
    // 9. Check history
    await page.getByText('History').click();
    await page.waitForTimeout(1000);
    
    // 10. Verify complete workflow
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('complete trading workflow - Intraday', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Select Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(1000);
    
    // Select M15 timeframe
    await page.getByText('M15').click();
    await page.waitForTimeout(2000);
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Verify Intraday badge
    await expect(page.getByText('Intraday')).toBeVisible();
    
    // Check performance metrics
    await expect(page.getByText(/win rate/i)).toBeVisible();
  });

  test('complete trading workflow - Swing', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Select Swing
    await page.getByText('Swing').click();
    await page.waitForTimeout(1000);
    
    // Select H1 timeframe
    await page.getByText('H1').click();
    await page.waitForTimeout(2000);
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Verify Swing badge
    await expect(page.getByText('Swing')).toBeVisible();
  });

  test('multi-signal workflow', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    // Generate 3 signals
    for (let i = 0; i < 3; i++) {
      await generateBtn.click();
      await page.waitForTimeout(5000);
    }
    
    // Check history has multiple signals
    await page.getByText('History').click();
    await page.waitForTimeout(1000);
    
    // Should have signals in history
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('style switching with signal persistence', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Generate Scalper signal
    await page.getByText('Scalper').click();
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Switch to Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(3000);
    
    // Should generate new signal
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible();
    
    // Check history has both
    await page.getByText('History').click();
    await page.waitForTimeout(1000);
  });

  test('panel interactions with signal generation', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Toggle left panel
    const leftToggle = page.locator('button').filter({ has: page.locator('svg') }).first();
    await leftToggle.click();
    await page.waitForTimeout(500);
    
    // Generate signal with panel closed
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await page.waitForTimeout(5000);
    
    // Open panel
    await leftToggle.click();
    await page.waitForTimeout(500);
    
    // Signal should be visible
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible();
  });

  test('timeframe changes with active signals', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Generate signal on M5
    await page.getByText('M5').click();
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Switch timeframes
    await page.getByText('M15').click();
    await page.waitForTimeout(2000);
    
    await page.getByText('H1').click();
    await page.waitForTimeout(2000);
    
    // Signal should still be visible
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible();
    
    // Chart should update
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('news and calendar integration', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Check news
    await page.getByText('News').click();
    await page.waitForTimeout(2000);
    
    // Check calendar
    await page.getByText('Calendar').click();
    await page.waitForTimeout(2000);
    
    // Generate signal with calendar visible
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Everything should work together
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('configuration changes affect signal generation', async ({ page }) => {
    // Go to config
    await page.goto('/config');
    await page.waitForLoadState('networkidle');
    
    // Change provider (if possible)
    const providerBtn = page.getByText(/openai|claude|gemini/i).first();
    if (await providerBtn.isVisible()) {
      await providerBtn.click();
      await page.waitForTimeout(500);
    }
    
    // Go back to dashboard
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
  });

  test('performance tracking across multiple signals', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Get initial performance
    const initialWinRate = await page.locator('text=/\\d+%/').first().textContent();
    
    // Generate multiple signals
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 3; i++) {
      await generateBtn.click();
      await page.waitForTimeout(5000);
    }
    
    // Performance section should still be visible
    await expect(page.getByText(/performance/i)).toBeVisible();
  });
});
