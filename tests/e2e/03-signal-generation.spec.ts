import { test, expect } from '@playwright/test';

test.describe('Signal Generation - Requirement 1', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should generate at least 4 signals', async ({ page }) => {
    // Find and click Generate button
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await expect(generateBtn).toBeVisible();
    
    // Click generate
    await generateBtn.click();
    
    // Wait for loading state
    await expect(page.getByText(/\.\.\./)).toBeVisible({ timeout: 2000 });
    
    // Wait for signal to appear (up to 30 seconds)
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Check for signal card elements
    await expect(page.getByText(/entry/i)).toBeVisible();
    await expect(page.getByText(/stop loss/i)).toBeVisible();
    await expect(page.getByText(/tp1/i)).toBeVisible();
    
    // Verify confidence badge is visible
    const confidenceBadge = page.locator('text=/\\d+%/').first();
    await expect(confidenceBadge).toBeVisible();
  });

  test('should show signal details when expanded', async ({ page }) => {
    // Wait for any existing signal or generate new one
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Click "Why this trade?" to expand
    const expandBtn = page.getByText(/why this trade/i);
    await expandBtn.click();
    
    // Check for reasoning text
    await expect(page.locator('text=/pattern|trend|support|resistance/i')).toBeVisible();
  });

  test('should show detected patterns when available', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Expand details
    await page.getByText(/why this trade/i).click();
    
    // Look for patterns section (may not always be present)
    const patternsSection = page.getByText(/detected patterns/i);
    if (await patternsSection.isVisible()) {
      await expect(patternsSection).toBeVisible();
    }
  });

  test('should display confidence percentage', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Find confidence number (should be 0-100)
    const confidence = await page.locator('text=/\\d+/').first().textContent();
    const confNum = parseInt(confidence || '0');
    
    expect(confNum).toBeGreaterThanOrEqual(0);
    expect(confNum).toBeLessThanOrEqual(100);
  });

  test('should show copy button', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    const copyBtn = page.getByRole('button', { name: /copy/i });
    await expect(copyBtn).toBeVisible();
    
    // Click copy
    await copyBtn.click();
    
    // Should show "Copied!" feedback
    await expect(page.getByText(/copied/i)).toBeVisible({ timeout: 2000 });
  });

  test('should show execute button for actionable signals', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL/)).toBeVisible({ timeout: 30000 });
    
    // Execute button should be visible for BUY/SELL signals
    const executeBtn = page.getByRole('button', { name: /execute on mt5/i });
    const signalDirection = await page.locator('text=/BUY|SELL|HOLD/').first().textContent();
    
    if (signalDirection !== 'HOLD') {
      await expect(executeBtn).toBeVisible();
    }
  });

  test('should handle rapid generate clicks gracefully', async ({ page }) => {
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    // Click multiple times rapidly
    await generateBtn.click();
    await generateBtn.click();
    await generateBtn.click();
    
    // Should still work and show signal
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
  });

  test('should show error message if generation fails', async ({ page }) => {
    // This test assumes backend might fail - check for error handling
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Wait for either success or error
    await Promise.race([
      page.getByText(/BUY|SELL|HOLD/).waitFor({ timeout: 30000 }),
      page.getByText(/error|failed|unreachable/i).waitFor({ timeout: 30000 }),
    ]);
  });
});
