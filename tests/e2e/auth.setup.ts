import fs from 'node:fs';
import path from 'node:path';
import { test as setup, expect } from '@playwright/test';
import { loginUser } from './helpers';

const authStatePath = path.join(__dirname, 'playwright', '.auth', 'user.json');

setup('authenticate shared smoke user', async ({ page }) => {
  setup.setTimeout(180_000);
  fs.mkdirSync(path.dirname(authStatePath), { recursive: true });

  await loginUser(page);
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15_000 });

  await page.context().storageState({ path: authStatePath });
});
