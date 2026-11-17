import { expect, test } from '@playwright/test';

const API_URL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8010';

test.beforeAll(async ({ request }) => {
  const health = await request.get(`${API_URL}/`);
  expect(health.ok(), 'Il backend deve essere avviato prima degli E2E').toBe(true);
  const body = await health.json();
  expect(body.status).toBe('ok');
});

test('login, aggiunta, completamento ed eliminazione dalla lista spesa', async ({ page }) => {
  const item = `E2E ${Date.now()}`;

  await page.goto('/');
  await expect(page.getByText('Chi sei oggi?')).toBeVisible();

  await page.getByText('Tu (Admin)', { exact: true }).click();
  await expect(page.getByText('Inserisci PIN')).toBeVisible();
  await page.getByPlaceholder('****').fill('0000');
  await page.getByText(/Sblocca/).click();

  await expect(page.getByText('BENVENUTO')).toBeVisible({ timeout: 20_000 });

  await page.getByText('Apri lista · aggiungi o completa').click();
  await expect(page.getByText('🛒 Lista spesa')).toBeVisible();

  const input = page.getByPlaceholder('Aggiungi latte, pane, frutta…');
  await input.fill(item);
  await input.press('Enter');
  await expect(page.getByText(item, { exact: true })).toBeVisible();

  await page.getByRole('button', { name: `Completa ${item}` }).click();
  await expect(page.getByText('Completati', { exact: true })).toBeVisible();
  await expect(page.getByText(item, { exact: true })).toBeVisible();

  page.once('dialog', async (dialog) => {
    await dialog.accept();
  });
  await page.getByLabel('Elimina elemento').last().click();
  await expect(page.getByText(item, { exact: true })).toHaveCount(0);
});

test('genera un PDF reale dalla schermata documenti', async ({ page }) => {
  await page.goto('/');
  await page.getByText('Tu (Admin)', { exact: true }).click();
  await page.getByPlaceholder('****').fill('0000');
  await page.getByText(/Sblocca/).click();
  await expect(page.getByText('BENVENUTO')).toBeVisible({ timeout: 20_000 });

  await page.getByText('PDF', { exact: true }).click();
  await expect(page.getByText('📄 Crea un PDF')).toBeVisible();
  await page.getByPlaceholder('Es. Riepilogo spese di novembre').fill('E2E PDF');
  await page
    .getByPlaceholder('Scrivi qui il testo del documento…')
    .fill('Documento generato dal test end-to-end di ATLAS AI.');
  await page.getByText('📄 Genera PDF').click();
  await expect(page.getByText(/Ultimo file:/)).toBeVisible({ timeout: 15_000 });
});
