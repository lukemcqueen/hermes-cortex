---
language: typescript
tags: [playwright, e2e, testing, browser]
title: Playwright End-to-End Testing
description: Complete guide to Playwright browser testing including page navigation, locators, assertions, screenshots, network mocking, mobile emulation, and CI integration
source: pattern
---

# Playwright End-to-End Testing

## Setup and Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ['html'],
    ['json', { outputFile: 'test-results/results.json' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['list']
  ],
  
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 13'] },
    },
  ],
  
  webServer: {
    command: 'npm run dev',
    port: 3000,
    timeout: 120 * 1000,
    reuseExistingServer: !process.env.CI,
  },
});
```

## Page Navigation and Basic Interactions

```typescript
import { test, expect } from '@playwright/test';

test.describe('Navigation and Basic Interactions', () => {
  test('should navigate to the home page', async ({ page }) => {
    await page.goto('/');
    
    // Verify the page loaded
    await expect(page).toHaveTitle(/My App/);
    await expect(page.locator('h1')).toContainText('Welcome');
    
    // Check URL
    await expect(page).toHaveURL(/.*\//);
  });
  
  test('should navigate between pages', async ({ page }) => {
    await page.goto('/');
    
    // Click a navigation link
    await page.getByRole('link', { name: 'About' }).click();
    
    // Wait for navigation and check URL
    await page.waitForURL('**/about');
    await expect(page.locator('h1')).toContainText('About Us');
    
    // Use browser back button
    await page.goBack();
    await expect(page).toHaveURL('/');
  });
  
  test('should fill and submit a form', async ({ page }) => {
    await page.goto('/contact');
    
    // Fill form fields
    await page.getByLabel('Name').fill('John Doe');
    await page.getByLabel('Email').fill('john@example.com');
    await page.getByLabel('Message').fill('Hello, this is a test message.');
    
    // Select from dropdown
    await page.getByLabel('Subject').selectOption('Support');
    
    // Check a checkbox
    await page.getByLabel('Subscribe to newsletter').check();
    
    // Submit the form
    await page.getByRole('button', { name: 'Submit' }).click();
    
    // Verify success message
    await expect(page.getByText('Thank you for your message')).toBeVisible();
  });
  
  test('should handle loading states', async ({ page }) => {
    await page.goto('/dashboard');
    
    // Wait for content to load (spinner disappeared)
    await expect(page.locator('.loading-spinner')).not.toBeVisible();
    
    // Wait for specific element
    await page.waitForSelector('[data-testid="dashboard-content"]', {
      state: 'visible',
      timeout: 10000
    });
    
    // Assert content is loaded
    await expect(page.getByTestId('dashboard-content')).toBeVisible();
  });
});
```

## Locators and Assertions

```typescript
import { test, expect } from '@playwright/test';

test.describe('Locators and Assertions', () => {
  test('should use various locator strategies', async ({ page }) => {
    await page.goto('/products');
    
    // By text
    await page.getByText('Featured Products').click();
    
    // By role (preferred for accessibility)
    await page.getByRole('button', { name: 'Add to Cart' }).first().click();
    
    // By test ID
    await page.getByTestId('checkout-button').click();
    
    // By label (for form fields)
    await page.getByLabel('Search products').fill('laptop');
    
    // By placeholder
    await page.getByPlaceholder('Enter your email').fill('test@example.com');
    
    // By CSS or XPath (fallback)
    await page.locator('.product-card').first().click();
    await page.locator('//div[@class="product-details"]').isVisible();
    
    // Chaining locators
    const productCard = page.locator('.product-card').filter({ hasText: 'Laptop' });
    await productCard.getByRole('button', { name: 'Details' }).click();
  });
  
  test('should use various assertions', async ({ page }) => {
    await page.goto('/profile');
    
    // Visibility
    await expect(page.getByText('Profile Settings')).toBeVisible();
    await expect(page.getByText('Hidden Section')).not.toBeVisible();
    
    // Text content
    await expect(page.locator('.username')).toHaveText('johndoe');
    await expect(page.locator('.username')).toContainText('john');
    
    // Attribute assertions
    await expect(page.locator('#avatar')).toHaveAttribute('src', /avatar\.jpg$/);
    await expect(page.getByLabel('Email')).toHaveValue('john@example.com');
    
    // Count assertions
    await expect(page.locator('.product-item')).toHaveCount(12);
    
    // CSS assertions
    await expect(page.locator('.error-message')).toHaveCSS('color', 'rgb(255, 0, 0)');
    
    // URL assertions
    await expect(page).toHaveURL(/.*\/profile$/);
    
    // Class assertions
    await expect(page.locator('.nav-item.active')).toHaveClass(/active/);
    
    // Enabled/disabled state
    await expect(page.getByRole('button', { name: 'Submit' })).toBeDisabled();
    await page.getByLabel('Name').fill('John');
    await expect(page.getByRole('button', { name: 'Submit' })).toBeEnabled();
  });
  
  test('should handle dynamic content', async ({ page }) => {
    await page.goto('/search');
    
    // Type and wait for suggestions
    await page.getByPlaceholder('Search...').pressSequentially('play', { delay: 100 });
    await page.waitForResponse(response => 
      response.url().includes('/api/search') && response.status() === 200
    );
    
    // Wait for element to appear
    await expect(page.locator('.search-suggestion')).toHaveCount(5);
    
    // Click on first suggestion
    await page.locator('.search-suggestion').first().click();
  });
});
```

## Screenshots and Visual Testing

```typescript
import { test, expect } from '@playwright/test';

test.describe('Screenshots and Visual Testing', () => {
  test('should take full page screenshot', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    await page.screenshot({
      path: 'screenshots/dashboard.png',
      fullPage: true,
    });
  });
  
  test('should take element screenshot', async ({ page }) => {
    await page.goto('/products');
    
    // Screenshot a specific element
    const productCard = page.locator('.product-card').first();
    await productCard.screenshot({
      path: 'screenshots/product-card.png',
    });
  });
  
  test('should capture specific viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 }); // iPhone X
    await page.goto('/responsive');
    
    await page.screenshot({
      path: 'screenshots/mobile-home.png',
      fullPage: true,
    });
  });
  
  test('visual comparison', async ({ page }) => {
    // Requires @playwright/test expect.extend or Visual Comparison plugin
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Visual snapshot comparison (using Playwright's built-in screenshot matching)
    await expect(page).toHaveScreenshot('home-page.png', {
      maxDiffPixels: 100,
      threshold: 0.2,
    });
  });
  
  test('should mask dynamic content in screenshots', async ({ page }) => {
    await page.goto('/profile');
    
    await page.screenshot({
      path: 'screenshots/profile-masked.png',
      mask: [
        page.locator('.user-avatar'),
        page.locator('.last-login-date'),
      ],
    });
  });
});
```

## Network Mocking

```typescript
import { test, expect } from '@playwright/test';

test.describe('Network Mocking', () => {
  test('should mock API responses', async ({ page }) => {
    // Mock a GET endpoint
    await page.route('**/api/products', async route => {
      const response = await route.fetch();
      const json = await response.json();
      
      // Modify the response
      json.push({
        id: 999,
        name: 'Mocked Product',
        price: 19.99,
      });
      
      await route.fulfill({ json });
    });
    
    await page.goto('/products');
    await expect(page.getByText('Mocked Product')).toBeVisible();
  });
  
  test('should mock failed API requests', async ({ page }) => {
    // Simulate a server error
    await page.route('**/api/user/profile', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal Server Error' }),
      });
    });
    
    await page.goto('/profile');
    
    // Verify error handling UI
    await expect(page.getByText('Something went wrong')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  });
  
  test('should intercept and block requests', async ({ page }) => {
    // Block analytics and tracking scripts
    await page.route('**/analytics.js', route => route.abort());
    await page.route('**/telemetry/**', route => route.abort());
    await page.route('**/facebook.net/**', route => route.abort());
    
    await page.goto('/');
    // Page should still work without analytics
    await expect(page.locator('h1')).toBeVisible();
  });
  
  test('should mock WebSocket connections', async ({ page }) => {
    // Mock WebSocket communication
    await page.routeWebSocket('**/ws/live-updates', ws => {
      ws.onMessage(message => {
        // Intercept incoming messages
        console.log('Received:', message);
      });
      
      // Send custom messages to the page
      ws.send(JSON.stringify({ type: 'update', data: { id: 1, status: 'active' } }));
    });
    
    await page.goto('/live-dashboard');
    await expect(page.getByText('Status: active')).toBeVisible();
  });
  
  test('should validate outgoing requests', async ({ page }) => {
    // Track API calls
    const apiRequests: string[] = [];
    
    await page.route('**/api/**', route => {
      apiRequests.push(route.request().url());
      route.continue();
    });
    
    await page.goto('/');
    await page.getByRole('button', { name: 'Load Data' }).click();
    
    // Verify the correct API was called
    expect(apiRequests).toContain(expect.stringContaining('/api/data'));
  });
});
```

## Mobile Emulation

```typescript
import { test, expect, devices } from '@playwright/test';

test.describe('Mobile Emulation', () => {
  test.use({ ...devices['iPhone 13'] });
  
  test('should display mobile layout', async ({ page }) => {
    await page.goto('/');
    
    // Mobile hamburger menu should be visible
    await expect(page.getByRole('button', { name: 'Menu' })).toBeVisible();
    
    // Desktop navigation should be hidden
    await expect(page.locator('.desktop-nav')).not.toBeVisible();
  });
  
  test('should handle touch interactions', async ({ page }) => {
    await page.goto('/gallery');
    
    // Swipe gesture (drag from right to left)
    await page.locator('.gallery-container').dragTo(
      page.locator('.gallery-container'),
      { sourcePosition: { x: 300, y: 200 }, targetPosition: { x: 50, y: 200 } }
    );
    
    // Verify carousel moved
    await expect(page.locator('.slide.active')).toHaveAttribute('data-index', '1');
  });
  
  test('should respect mobile viewport', async ({ page }) => {
    await page.goto('/');
    
    // Check viewport size
    const viewport = page.viewportSize();
    expect(viewport?.width).toBe(390);  // iPhone 13 width
    expect(viewport?.height).toBe(844); // iPhone 13 height
    
    // Responsive elements
    const button = page.getByRole('button', { name: 'Submit' });
    const buttonBox = await button.boundingBox();
    expect(buttonBox?.width).toBeGreaterThanOrEqual(300); // Full-width on mobile
  });
});

test.describe('Tablet Layout', () => {
  test.use({ ...devices['iPad Pro 11'] });
  
  test('should display tablet layout', async ({ page }) => {
    await page.goto('/dashboard');
    
    // Tablet shows a 2-column layout
    await expect(page.locator('.dashboard-grid')).toHaveCSS('grid-template-columns', /repeat\(2/);
  });
});
```

## Authentication Flows

```typescript
import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Authentication', () => {
  // Store auth state for reuse
  test.use({ storageState: 'e2e/.auth/user.json' });
  
  test('should login successfully', async ({ page }) => {
    await page.goto('/login');
    
    await page.getByLabel('Email').fill('user@example.com');
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    // Verify redirect to dashboard
    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByText('Welcome back, User')).toBeVisible();
  });
  
  test('should show validation errors', async ({ page }) => {
    await page.goto('/login');
    
    // Submit empty form
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    // Check validation messages
    await expect(page.getByText('Email is required')).toBeVisible();
    await expect(page.getByText('Password is required')).toBeVisible();
  });
  
  test('should handle invalid credentials', async ({ page }) => {
    await page.goto('/login');
    
    await page.getByLabel('Email').fill('wrong@example.com');
    await page.getByLabel('Password').fill('wrongpassword');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Invalid email or password')).toBeVisible();
  });
  
  test('should persist authentication via storage state', async ({ page }) => {
    // Save authentication state
    await page.goto('/login');
    await page.getByLabel('Email').fill('user@example.com');
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await page.context().storageState({ path: 'e2e/.auth/user.json' });
    
    // Next test can use storageState to skip login
  });
});
```

## CI Integration

```yaml
# .github/workflows/playwright.yml
name: Playwright E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    timeout-minutes: 60
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        browser: [chromium, firefox, webkit]
      fail-fast: false
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Install Playwright browsers
        run: npx playwright install --with-deps ${{ matrix.browser }}
      
      - name: Run Playwright tests
        run: npx playwright test --project=${{ matrix.browser }}
        env:
          BASE_URL: http://localhost:3000
      
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report-${{ matrix.browser }}
          path: playwright-report/
          retention-days: 30
      
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: test-results-${{ matrix.browser }}
          path: test-results/
          retention-days: 7
```

## Custom Fixtures and Hooks

```typescript
// fixtures.ts
import { test as base, expect, Page } from '@playwright/test';

// Custom fixture for authenticated user
type MyFixtures = {
  authenticatedPage: Page;
  user: { id: string; name: string; email: string };
};

export const test = base.extend<MyFixtures>({
  user: async ({}, use) => {
    // Setup: Create a test user
    const user = {
      id: 'test-123',
      name: 'Test User',
      email: 'test@example.com',
    };
    await use(user);
    // Teardown: Clean up test user
    // await deleteTestUser(user.id);
  },
  
  authenticatedPage: async ({ browser, user }, use) => {
    const context = await browser.newContext({
      storageState: 'e2e/.auth/user.json',
    });
    const page = await context.newPage();
    
    // Add custom methods
    page.getByTestId = (testId: string) => page.locator(`[data-testid="${testId}"]`);
    
    await use(page);
    await context.close();
  },
});

export { expect };


// Using custom fixtures in tests
// test.spec.ts
import { test, expect } from './fixtures';

test.describe('With Custom Fixtures', () => {
  test('should work with authenticated page', async ({ authenticatedPage, user }) => {
    await authenticatedPage.goto('/dashboard');
    await expect(authenticatedPage.getByText(`Welcome, ${user.name}`)).toBeVisible();
  });
  
  test('should access user fixture', async ({ user }) => {
    expect(user.email).toBe('test@example.com');
  });
});
```

## Advanced Patterns

```typescript
import { test, expect } from '@playwright/test';

test.describe('Advanced Patterns', () => {
  test('should handle file downloads', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download Report' }).click(),
    ]);
    
    const path = await download.path();
    const suggestedName = download.suggestedFilename();
    
    expect(suggestedName).toContain('report');
    expect(path).toBeTruthy();
    
    // Save to specific location
    await download.saveAs(`./downloads/${suggestedName}`);
  });
  
  test('should handle file uploads', async ({ page }) => {
    await page.goto('/upload');
    
    // Upload single file
    await page.getByLabel('Upload file').setInputFiles('tests/fixtures/test.pdf');
    
    // Upload multiple files
    await page.getByLabel('Upload files').setInputFiles([
      'tests/fixtures/image1.jpg',
      'tests/fixtures/image2.jpg',
    ]);
    
    // Verify upload previews
    await expect(page.locator('.file-preview')).toHaveCount(2);
    
    // Submit and verify
    await page.getByRole('button', { name: 'Upload' }).click();
    await expect(page.getByText('Upload successful')).toBeVisible();
  });
  
  test('should handle dialogs', async ({ page }) => {
    // Handle alert dialog
    page.on('dialog', async dialog => {
      expect(dialog.type()).toBe('alert');
      expect(dialog.message()).toContain('Are you sure?');
      await dialog.accept();
    });
    
    await page.getByRole('button', { name: 'Delete Account' }).click();
  });
  
  test('should handle frames', async ({ page }) => {
    await page.goto('/with-iframe');
    
    const frame = page.frame({ url: /external-widget/ });
    await frame?.getByRole('button', { name: 'Widget Button' }).click();
    
    // Or by locator
    const iframeLocator = page.frameLocator('#external-iframe');
    await iframeLocator.getByPlaceholder('Search').fill('test');
  });
  
  test('should wait for multiple conditions', async ({ page }) => {
    await page.goto('/dashboard');
    
    // Wait for multiple elements
    await Promise.all([
      page.waitForSelector('[data-testid="revenue-chart"]'),
      page.waitForSelector('[data-testid="user-count"]'),
      page.waitForSelector('[data-testid="active-sessions"]'),
    ]);
    
    // Assert all dashboard widgets are loaded
    await expect(page.getByTestId('revenue-chart')).toBeVisible();
    await expect(page.getByTestId('user-count')).toBeVisible();
    await expect(page.getByTestId('active-sessions')).toBeVisible();
  });
});
```