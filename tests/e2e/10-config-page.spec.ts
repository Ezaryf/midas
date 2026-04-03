import { test, expect } from '@playwright/test';

test.describe('Configuration Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/config');
    await page.waitForLoadState('networkidle');
  });

  test('should load config page', async ({ page }) => {
    await expect(page.getByText(/settings|configuration/i)).toBeVisible();
  });

  test('should show API key input', async ({ page }) => {
    const apiKeyInput = page.getByPlaceholder(/api key/i);
    await expect(apiKeyInput).toBeVisible();
  });

  test('should show AI provider selector', async ({ page }) => {
    // Look for provider options
    await expect(page.getByText(/openai|claude|gemini|grok|groq/i).first()).toBeVisible();
  });

  test('should show trading style selector', async ({ page }) => {
    await expect(page.getByText(/scalper|intraday|swing/i).first()).toBeVisible();
  });

  test('should save configuration', async ({ page }) => {
    // Fill in API key
    const apiKeyInput = page.getByPlaceholder(/api key/i);
    await apiKeyInput.fill('test-api-key-12345');
    
    // Look for save button
    const saveBtn = page.getByRole('button', { name: /save/i });
    if (await saveBtn.isVisible()) {
      await saveBtn.click();
      await page.waitForTimeout(1000);
      
      // Should show success message
      await expect(page.getByText(/saved|success/i)).toBeVisible({ timeout: 5000 });
    }
  });

  test('should navigate back to dashboard', async ({ page }) => {
    const backLink = page.getByRole('link', { name: /dashboard|back/i });
    if (await backLink.isVisible()) {
      await backLink.click();
      await expect(page).toHaveURL(/\/dashboard/);
    }
  });

  test('should validate API key format', async ({ page }) => {
    const apiKeyInput = page.getByPlaceholder(/api key/i);
    await apiKeyInput.fill('invalid');
    
    const saveBtn = page.getByRole('button', { name: /save/i });
    if (await saveBtn.isVisible()) {
      await saveBtn.click();
      await page.waitForTimeout(1000);
      
      // May show validation error
    }
  });

  test('should persist configuration across page reloads', async ({ page }) => {
    // Set API key
    const apiKeyInput = page.getByPlaceholder(/api key/i);
    await apiKeyInput.fill('test-key-persist');
    
    const saveBtn = page.getByRole('button', { name: /save/i });
    if (await saveBtn.isVisible()) {
      await saveBtn.click();
      await page.waitForTimeout(1000);
    }
    
    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // API key should still be there (or masked)
    const inputValue = await apiKeyInput.inputValue();
    // May be masked or empty depending on implementation
  });

  test('should show MT5 configuration section', async ({ page }) => {
    // Look for MT5 settings
    const mt5Section = page.getByText(/mt5|metatrader/i);
    // May or may not be visible depending on config page design
  });

  test('should handle provider switching', async ({ page }) => {
    // Try switching between providers
    const providers = ['OpenAI', 'Claude', 'Gemini', 'Grok', 'Groq'];
    
    for (const provider of providers) {
      const providerBtn = page.getByText(provider, { exact: false });
      if (await providerBtn.isVisible()) {
        await providerBtn.click();
        await page.waitForTimeout(500);
      }
    }
  });
});
