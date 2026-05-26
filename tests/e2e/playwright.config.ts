import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const e2eBypassSecret = (process.env.E2E_RATE_LIMIT_BYPASS_SECRET || '').trim();
const e2eExtraHeaders: Record<string, string> = {
  'x-forwarded-proto': 'https',
};
if (e2eBypassSecret && (process.env.E2E_RATE_LIMIT_BYPASS || '').trim() === '1') {
  e2eExtraHeaders['x-e2e-rate-limit-bypass'] = e2eBypassSecret;
}
const configuredRetries = Number.parseInt(process.env.PW_RETRIES || '', 10);
const retries = Number.isInteger(configuredRetries) && configuredRetries >= 0
  ? configuredRetries
  : (process.env.CI ? 2 : 1);
const authStatePath = path.join(__dirname, 'playwright', '.auth', 'user.json');
const browserLibPath = path.join(__dirname, '.deps', 'sysroot', 'usr', 'lib', 'x86_64-linux-gnu');
const browserEnv = {
  ...process.env,
  LD_LIBRARY_PATH: process.env.LD_LIBRARY_PATH
    ? `${browserLibPath}:${process.env.LD_LIBRARY_PATH}`
    : browserLibPath,
};
const enableWebkit = process.env.PW_ENABLE_WEBKIT === '1';

const localBaseUrlPattern = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i;
const isLocalServer = localBaseUrlPattern.test(baseURL);

const projects = [
  {
    name: 'setup-auth',
    testMatch: /auth\.setup\.ts/,
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      launchOptions: {
        env: browserEnv,
        args: [
          '--disable-dev-shm-usage',
          '--js-flags=--max-old-space-size=4096',
        ],
      },
    },
  },
  {
    name: 'auth-chromium',
    testMatch: /auth-smoke\.spec\.ts/,
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'admin-chromium',
    testMatch: /admin-smoke\.spec\.ts/,
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'workspace-desktop-chromium',
    testMatch: /service-shell-.*\.spec\.ts/,
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'smoke-desktop-chromium',
    testMatch: /critical-smoke\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'react-vehicle-list-gated',
    testMatch: /react-vehicle-list-gated\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'vin-preview-smoke',
    testMatch: /vehicle-vin-preview\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'tutorials-desktop-chromium',
    testMatch: /tutorials\.spec\.ts/,
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      launchOptions: {
        env: browserEnv,
        args: ['--disable-dev-shm-usage'],
      },
    },
  },
  {
    name: 'smoke-desktop-firefox',
    testMatch: /critical-smoke\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Desktop Firefox'],
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'smoke-mobile-chromium',
    testMatch: /responsive-smoke\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Pixel 5'],
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
  {
    name: 'smoke-tablet-chromium',
    testMatch: /responsive-smoke\.spec\.ts/,
    dependencies: ['setup-auth'],
    use: {
      ...devices['Desktop Chrome'],
      viewport: { width: 834, height: 1112 },
      hasTouch: true,
      baseURL,
      storageState: authStatePath,
      launchOptions: {
        env: browserEnv,
      },
    },
  },
];

if (enableWebkit) {
  projects.push(
    {
      name: 'smoke-desktop-webkit',
      testMatch: /critical-smoke\.spec\.ts/,
      dependencies: ['setup-auth'],
      use: {
        ...devices['Desktop Safari'],
        baseURL,
        storageState: authStatePath,
        launchOptions: {
          env: browserEnv,
        },
      },
    },
    {
      name: 'smoke-mobile-safari',
      testMatch: /responsive-smoke\.spec\.ts/,
      dependencies: ['setup-auth'],
      use: {
        ...devices['iPhone 12'],
        baseURL,
        storageState: authStatePath,
        launchOptions: {
          env: browserEnv,
        },
      },
    },
  );
}

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  outputDir: 'test-results',
  reporter: [
    ['html', { outputFolder: '../../artifacts/qa/playwright-report', open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL,
    ignoreHTTPSErrors: isLocalServer,
    extraHTTPHeaders: isLocalServer ? e2eExtraHeaders : undefined,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    headless: true,
    launchOptions: {
      env: browserEnv,
    },
  },
  projects,
  webServer: isLocalServer
    ? {
        command: 'cd ../.. && . .venv/bin/activate && python3 -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000',
        url: `${baseURL}/health`,
        reuseExistingServer: true,
        timeout: 180 * 1000,
      }
    : undefined,
});
