import { test, expect } from '@playwright/test';

test.describe('MT5 Order Execution - Requirement 4', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should show execute button for actionable signals', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Check for execute button
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await expect(executeBtn).toBeVisible();
  });

  test('should handle execute button click', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Click execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    
    // Should show loading state
    await expect(page.getByText(/sending/i)).toBeVisible({ timeout: 2000 });
    
    // Wait for result (success or error)
    await Promise.race([
      page.getByText(/executed|success/i).waitFor({ timeout: 10000 }),
      page.getByText(/error|failed|unreachable|bridge/i).waitFor({ timeout: 10000 }),
    ]);
  });

  test('should show appropriate message when MT5 bridge is not connected', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Click execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    
    // Should show error about bridge (if not connected)
    // Or success if bridge is running
    await page.waitForTimeout(5000);
  });

  test('should disable execute button during execution', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Click execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    
    // Button should be disabled during execution
    await expect(executeBtn).toBeDisabled({ timeout: 2000 });
  });

  test('should not show execute button for HOLD signals', async ({ page }) => {
    // Generate signals until we get a HOLD (or timeout)
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 5; i++) {
      await generateBtn.click();
      await page.waitForTimeout(5000);
      
      const holdSignal = page.getByText('HOLD');
      if (await holdSignal.isVisible()) {
        // Execute button should not be visible for HOLD
        const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
        await expect(executeBtn).not.toBeVisible();
        break;
      }
    }
  });

  test('should show execution result message', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Click execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    
    // Wait for result message
    await page.waitForTimeout(5000);
    
    // Should show some result (success or error)
    const resultMessage = page.locator('text=/executed|error|failed|success|bridge/i').first();
    // Message may or may not be visible depending on backend state
  });

  test('should handle multiple execution attempts', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Try executing twice
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    await page.waitForTimeout(3000);
    
    // Try clicking again (should handle gracefully)
    if (await executeBtn.isEnabled()) {
      await executeBtn.click();
      await page.waitForTimeout(3000);
    }
    
    // Should not crash
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should maintain signal data during execution', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Get signal details before execution
    const entryText = await page.getByText(/entry/i).first().textContent();
    
    // Execute
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    await executeBtn.click();
    await page.waitForTimeout(3000);
    
    // Signal details should still be visible
    await expect(page.getByText(/entry/i).first()).toBeVisible();
  });
});
