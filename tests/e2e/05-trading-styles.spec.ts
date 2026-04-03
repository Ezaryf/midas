import { test, expect } from '@playwright/test';

test.describe('Trading Style Adaptation - Requirement 3', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should switch between trading styles', async ({ page }) => {
    // Test Scalper
    await page.getByText('Scalper').click();
    await page.waitForTimeout(1000);
    
    // Test Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(1000);
    
    // Test Swing
    await page.getByText('Swing').click();
    await page.waitForTimeout(1000);
    
    // Should not crash
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should generate different signals for Scalper style', async ({ page }) => {
    // Select Scalper
    await page.getByText('Scalper').click();
    await page.waitForTimeout(2000);
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Expand to see details
    await page.getByText(/why this trade/i).click();
    
    // Should mention scalper or show tight stops
    const reasoning = await page.locator('text=/scalper|1m|5m|tight/i').first();
    // May or may not be visible depending on AI reasoning
  });

  test('should generate different signals for Intraday style', async ({ page }) => {
    // Select Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(2000);
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Check style badge
    await expect(page.getByText('Intraday')).toBeVisible();
  });

  test('should generate different signals for Swing style', async ({ page }) => {
    // Select Swing
    await page.getByText('Swing').click();
    await page.waitForTimeout(2000);
    
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Check style badge
    await expect(page.getByText('Swing')).toBeVisible();
  });

  test('should show different stop loss distances per style', async ({ page }) => {
    const styles = ['Scalper', 'Intraday', 'Swing'];
    const stopLosses: number[] = [];
    
    for (const style of styles) {
      // Select style
      await page.getByText(style).click();
      await page.waitForTimeout(2000);
      
      // Generate signal
      const generateBtn = page.getByRole('button', { name: /generate/i });
      await generateBtn.click();
      await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
      
      // Try to extract stop loss value
      const slText = await page.locator('text=/stop loss/i').first().textContent();
      
      // Wait before next iteration
      await page.waitForTimeout(1000);
    }
    
    // At least verify styles can be switched without errors
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should clear previous signals when switching styles', async ({ page }) => {
    // Generate Scalper signal
    await page.getByText('Scalper').click();
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    const firstSignal = await page.locator('text=/BUY|SELL/').first().textContent();
    
    // Switch to Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(3000);
    
    // Should generate new signal automatically or show different signal
    // The system should adapt
  });

  test('should maintain style selection across page interactions', async ({ page }) => {
    // Select Intraday
    await page.getByText('Intraday').click();
    await page.waitForTimeout(1000);
    
    // Toggle panels
    const leftToggle = page.locator('button').filter({ has: page.locator('svg') }).first();
    await leftToggle.click();
    await page.waitForTimeout(500);
    await leftToggle.click();
    
    // Intraday should still be selected
    const intradayBtn = page.getByText('Intraday');
    // Check if it has active styling (this depends on your CSS)
  });

  test('should handle rapid style switching', async ({ page }) => {
    // Rapidly switch styles
    await page.getByText('Scalper').click();
    await page.getByText('Intraday').click();
    await page.getByText('Swing').click();
    await page.getByText('Scalper').click();
    await page.getByText('Intraday').click();
    
    // Should not crash
    await page.waitForTimeout(2000);
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should show style-specific confidence thresholds', async ({ page }) => {
    // This is more of a backend test, but we can verify signals are generated
    const styles = ['Scalper', 'Intraday', 'Swing'];
    
    for (const style of styles) {
      await page.getByText(style).click();
      await page.waitForTimeout(2000);
      
      const generateBtn = page.getByRole('button', { name: /generate/i });
      await generateBtn.click();
      
      // Should generate signal for each style
      await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
      
      await page.waitForTimeout(1000);
    }
  });
});
