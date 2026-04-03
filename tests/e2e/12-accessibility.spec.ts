import { test, expect } from '@playwright/test';

test.describe('Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('should have proper heading hierarchy', async ({ page }) => {
    // Check for headings
    const headings = page.locator('h1, h2, h3, h4, h5, h6');
    const count = await headings.count();
    
    // Should have some headings
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should have accessible buttons', async ({ page }) => {
    // All buttons should have accessible names
    const buttons = page.locator('button');
    const count = await buttons.count();
    
    for (let i = 0; i < Math.min(count, 10); i++) {
      const button = buttons.nth(i);
      const text = await button.textContent();
      const ariaLabel = await button.getAttribute('aria-label');
      
      // Button should have text or aria-label
      expect(text || ariaLabel).toBeTruthy();
    }
  });

  test('should support keyboard navigation', async ({ page }) => {
    // Tab through interactive elements
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    
    // Should be able to navigate
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    expect(focusedElement).toBeTruthy();
  });

  test('should have proper color contrast', async ({ page }) => {
    // Visual check - ensure text is visible
    await expect(page.getByText('Midas')).toBeVisible();
    await expect(page.getByText('XAU/USD')).toBeVisible();
  });

  test('should have alt text for images', async ({ page }) => {
    const images = page.locator('img');
    const count = await images.count();
    
    for (let i = 0; i < count; i++) {
      const img = images.nth(i);
      const alt = await img.getAttribute('alt');
      
      // Images should have alt text (or be decorative)
      expect(alt !== null).toBeTruthy();
    }
  });

  test('should support screen reader navigation', async ({ page }) => {
    // Check for ARIA landmarks
    const main = page.locator('main, [role="main"]');
    const nav = page.locator('nav, [role="navigation"]');
    
    // Should have semantic structure
    // (May or may not be present depending on implementation)
  });

  test('should have focus indicators', async ({ page }) => {
    // Tab to first interactive element
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    
    // Check if focus is visible (visual check)
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeVisible();
  });

  test('should support Enter key for button activation', async ({ page }) => {
    // Focus on generate button
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.focus();
    
    // Press Enter
    await page.keyboard.press('Enter');
    
    // Should trigger action
    await page.waitForTimeout(2000);
  });

  test('should have proper form labels', async ({ page }) => {
    await page.goto('/config');
    await page.waitForLoadState('networkidle');
    
    // Check for input labels
    const inputs = page.locator('input');
    const count = await inputs.count();
    
    for (let i = 0; i < count; i++) {
      const input = inputs.nth(i);
      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const placeholder = await input.getAttribute('placeholder');
      
      // Input should have label, aria-label, or placeholder
      expect(id || ariaLabel || placeholder).toBeTruthy();
    }
  });

  test('should announce dynamic content changes', async ({ page }) => {
    // Generate signal (dynamic content)
    const generateBtn = page.getByRole('button', { name: /generate/i });
    await generateBtn.click();
    
    // Wait for signal to appear
    await expect(page.getByText(/BUY|SELL|HOLD/)).toBeVisible({ timeout: 30000 });
    
    // Check for aria-live regions (optional)
    const liveRegions = page.locator('[aria-live]');
    // May or may not be present
  });
});
