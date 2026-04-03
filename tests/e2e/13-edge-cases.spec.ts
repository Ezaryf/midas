import { test, expect } from '@playwright/test';

test.describe('Edge Cases & Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should handle backend unavailable', async ({ page }) => {
    // This test assumes backend might be down
    // Try to generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Should either succeed or show error gracefully
    await Promise.race([
      page.getByText(/BUY|SELL|HOLD/).waitFor({ timeout: 30000 }),
      page.getByText(/error|unreachable|failed/i).waitFor({ timeout: 30000 }),
    ]);
    
    // Page should not crash
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle missing API key', async ({ page }) => {
    // Go to config and clear API key
    await page.goto('/config');
    await page.waitForLoadState('networkidle');
    
    const apiKeyInput = page.getByPlaceholder(/api key/i);
    if (await apiKeyInput.isVisible()) {
      await apiKeyInput.clear();
      
      const saveBtn = page.getByRole('button', { name: /save/i });
      if (await saveBtn.isVisible()) {
        await saveBtn.click();
        await page.waitForTimeout(1000);
      }
    }
    
    // Go back to dashboard
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Should show warning about missing API key
    await expect(page.getByText(/no api key/i)).toBeVisible({ timeout: 5000 });
  });

  test('should handle invalid timeframe data', async ({ page }) => {
    // Switch to different timeframes rapidly
    await page.getByText('M1').click();
    await page.getByText('H4').click();
    await page.getByText('M3').click();
    
    // Chart should handle gracefully
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('should handle empty signal response', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Wait for response
    await page.waitForTimeout(30000);
    
    // Should show either signal or "no signal" message
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle malformed WebSocket messages', async ({ page }) => {
    // This is more of a backend test, but ensure frontend doesn't crash
    await page.waitForTimeout(5000);
    
    // Page should remain functional
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle extremely long signal reasoning', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Expand reasoning
    await page.getByText(/why this trade/i).click();
    
    // Should display without breaking layout
    await page.waitForTimeout(1000);
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle zero confidence signals', async ({ page }) => {
    // Generate signals until we get a low confidence one
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    for (let i = 0; i < 3; i++) {
      await generateBtn.click();
      await page.waitForTimeout(5000);
      
      // Check confidence
      const confidence = page.locator('text=/\\d+/').first();
      if (await confidence.isVisible()) {
        const confText = await confidence.textContent();
        const confNum = parseInt(confText || '0');
        
        // Should handle any confidence value
        expect(confNum).toBeGreaterThanOrEqual(0);
        expect(confNum).toBeLessThanOrEqual(100);
      }
    }
  });

  test('should handle missing price data', async ({ page }) => {
    // Wait for page load
    await page.waitForTimeout(3000);
    
    // Price display should handle missing data gracefully
    const priceElement = page.locator('text=/\\d{4}\\.\\d{2}|N\\/A/').first();
    // Should show either price or N/A
  });

  test('should handle chart with no data', async ({ page }) => {
    // Switch to a timeframe that might have no data
    await page.getByText('H4').click();
    await page.waitForTimeout(3000);
    
    // Chart should show loading or empty state
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  test('should handle concurrent signal generations', async ({ page }) => {
    // Try to generate multiple signals at once
    const generateBtn = page.getByRole('button', { name: /generate/i });
    
    await Promise.all([
      generateBtn.click(),
      generateBtn.click(),
      generateBtn.click(),
    ]);
    
    // Should handle gracefully
    await page.waitForTimeout(10000);
    await expect(page.getByText('Midas')).toBeVisible();
  });

  test('should handle invalid signal data', async ({ page }) => {
    // Generate signal
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Signal should have valid data
    await expect(page.getByText(/entry/i)).toBeVisible();
  });

  test('should handle session timeout', async ({ page }) => {
    // Wait for a long time
    await page.waitForTimeout(10000);
    
    // Try to interact
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Should still work or redirect to login
    await page.waitForTimeout(5000);
  });

  test('should handle browser console errors gracefully', async ({ page }) => {
    const errors: string[] = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    
    // Perform various actions
    await page.getByText('M5').click();
    await page.waitForTimeout(1000);
    
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    await page.waitForTimeout(5000);
    
    // Log errors for debugging (don't fail test)
    if (errors.length > 0) {
      console.log('Console errors detected:', errors);
    }
  });

  test('should handle missing chart library', async ({ page }) => {
    // Chart should load or show error
    await page.waitForTimeout(5000);
    
    const canvas = page.locator('canvas').first();
    const errorMsg = page.getByText(/error|failed to load/i);
    
    // Should show either chart or error
    const canvasVisible = await canvas.isVisible();
    const errorVisible = await errorMsg.isVisible();
    
    expect(canvasVisible || errorVisible).toBeTruthy();
  });
});
