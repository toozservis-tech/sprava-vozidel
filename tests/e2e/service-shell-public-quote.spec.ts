import { expect, test } from '@playwright/test';

test.describe('Public quote page', () => {
  test('shows quote and approves it on mobile', async ({ page }) => {
    let status = 'sent';

    await page.route('**/api/public/quote/quote-public-token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          quote_id: 801,
          vehicle_label: 'Skoda Octavia',
          service_name: 'ToozServis',
          service_ico: '12345678',
          items: [
            { name: 'Výměna oleje', quantity: 1, unit_price: 3490, total_price: 3490 },
          ],
          labor_hours: 1.5,
          labor_rate: 890,
          total_price: 3490,
          status,
          status_label: status === 'approved' ? 'Schváleno' : 'Odesláno',
          decision_available: status !== 'approved' && status !== 'rejected',
          created_at: '2026-04-15T12:00:00Z',
        }),
      });
    });

    await page.route('**/api/public/quote/quote-public-token/approve', async (route) => {
      status = 'approved';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'approved',
          message: 'Nabídka byla schválena.',
        }),
      });
    });

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/web/public-quote.html?token=quote-public-token');

    await expect(page.getByText('Skoda Octavia')).toBeVisible();
    await expect(page.getByText('ToozServis')).toBeVisible();
    await expect(page.getByText('Výměna oleje')).toBeVisible();
    await page.getByRole('button', { name: 'Schválit' }).click();
    await expect(page.getByText('Nabídka byla schválena.')).toBeVisible();
    await expect(page.getByText('Schváleno')).toBeVisible();
  });
});
