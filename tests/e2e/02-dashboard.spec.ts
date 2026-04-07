import { test, expect } from '@playwright/test';

test.describe('Dashboard - Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Skip auth for now - adjust if you have test credentials
    await page.goto('/dashboard');
  });

  test('should load dashboard with all main components', async ({ page }) => {
    // Wait for page to be fully loaded
    await page.waitForLoadState('networkidle');
    
    // Check header elements
    await expect(page.getByText('Midas')).toBeVisible();
    await expect(page.getByText('XAU/USD')).toBeVisible();
    
    // Check timeframe selector
    await expect(page.getByText('M1')).toBeVisible();
    await expect(page.getByText('M5')).toBeVisible();
    await expect(page.getByText('M15')).toBeVisible();
    
    // Check trading style selector
    await expect(page.getByText('Scalper')).toBeVisible();
    await expect(page.getByText('Intraday')).toBeVisible();
    await expect(page.getByText('Swing')).toBeVisible();
    
    // Check for chart container
    const chart = page.locator('canvas').first();
    await expect(chart).toBeVisible({ timeout: 10000 });
  });

  test('should show connection status indicator', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Look for Live/Offline indicator
    const status = page.getByText(/live|offline/i);
    await expect(status).toBeVisible();
  });

  test('should display performance metrics', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Check for performance indicators in header
    await expect(page.getByText(/win/i)).toBeVisible();
    await expect(page.getByText(/sig/i)).toBeVisible();
    await expect(page.getByText(/p&l/i)).toBeVisible();
  });

  test('should have settings link', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    const settingsLink = page.getByRole('link', { name: /settings/i });
    await expect(settingsLink).toBeVisible();
  });

  test('should toggle left panel', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Find toggle button (chevron icon)
    const toggleButton = page.locator('button').filter({ has: page.locator('svg') }).first();
    
    // Click to close
    await toggleButton.click();
    await page.waitForTimeout(500); // Wait for animation
    
    // Click to open
    await toggleButton.click();
    await page.waitForTimeout(500);
  });

  test('should toggle right panel', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Find right panel toggle
    const toggleButtons = page.locator('button').filter({ has: page.locator('svg') });
    const rightToggle = toggleButtons.last();
    
    await rightToggle.click();
    await page.waitForTimeout(500);
    
    await rightToggle.click();
    await page.waitForTimeout(500);
  });
});
