const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('../ui/node_modules/playwright'); } catch { playwright = require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'artifacts/design');
const base = 'http://127.0.0.1:3000';
const assert = (ok, message) => { if (!ok) throw new Error(message); };
(async () => {
  const browser = await playwright.chromium.launch({ headless: true, executablePath: path.join(process.env.USERPROFILE, 'AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe') });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
  const page = await context.newPage();
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: width === 1440 ? 1080 : 844 });
    await page.goto(base); await page.waitForLoadState('networkidle');
    const assistant = await page.locator('#ordering-assistant').boundingBox();
    const input = await page.getByRole('textbox', { name: '向点餐助手提问' }).boundingBox();
    assert(assistant.y < 844 && input.y + input.height < (width === 1440 ? 1080 : 844), `Assistant not usable in first screen at ${width}`);
    await page.screenshot({ path: path.join(out, `first-screen-${width}.png`) });
    checks.push({ name: `First screen interactive assistant at ${width}`, passed: true });
  }
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto(base); await page.waitForLoadState('networkidle');
  const photos = page.locator('.dish-card .dish-visual img');
  assert(await photos.count() === 14, 'Missing dish images');
  for (const photo of await photos.all()) { await photo.scrollIntoViewIfNeeded(); await photo.evaluate(img => img.decode()); }
  assert(await page.locator('.dish-card .ai-image-badge').count() === 14, 'AI image provenance missing');
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(out, 'food-home-full.png'), fullPage: true });
  checks.push({ name: '14 independent dish images load and show provenance', passed: true });

  let fail = false, savedPayload = null, starts = 0;
  await page.route('**/api/admin/menu/image-jobs', route => { starts++; return route.fulfill({ json: { job_id: 'mock-image-flow', status: 'queued', message: '测试生成进度' } }); });
  await page.route('**/api/admin/menu/image-jobs/mock-image-flow', route => route.fulfill({ json: fail ? { job_id: 'mock-image-flow', status: 'failed', message: '测试：生成服务繁忙，请重试' } : { job_id: 'mock-image-flow', status: 'succeeded', image_url: '/images/generated/menu-1.webp', message: '已生成' } }));
  await page.route('**/api/admin/menu', async route => {
    assert(route.request().method() === 'POST', 'Unexpected menu mutation');
    savedPayload = route.request().postDataJSON();
    return route.fulfill({ json: { id: -1, ...savedPayload } });
  });
  await page.goto(base + '/admin/menu'); await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '添加菜品' }).click();
  const dialog = page.getByRole('dialog', { name: '添加菜品' });
  await dialog.getByPlaceholder('如：宫保鸡丁').fill('自动配图验收');
  assert(await dialog.getByLabel('保存时自动生成缺失图片').isChecked(), 'Auto-image is not enabled by default');
  await dialog.getByRole('button', { name: '保存菜品', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert(savedPayload?.image_url === '/images/generated/menu-1.webp' && starts === 1, 'Dish saved without awaiting generated image');
  checks.push({ name: 'Add dish waits for generation then saves its local image (mock provider and save)', passed: true });

  fail = true; savedPayload = null;
  await page.getByRole('button', { name: '添加菜品' }).click();
  await dialog.getByPlaceholder('如：宫保鸡丁').fill('失败重试验收');
  await dialog.getByRole('button', { name: '保存菜品', exact: true }).click();
  await dialog.getByRole('alert').filter({ hasText: '测试：生成服务繁忙' }).waitFor();
  assert(!savedPayload, 'Failed image generation still created a menu item');
  checks.push({ name: 'Generation failure is visible and prevents silent save', passed: true });
  fail = false;
  await dialog.getByRole('button', { name: 'AI 生成菜品图片', exact: true }).click();
  await dialog.locator('.image-editor-preview img').waitFor();
  assert(await dialog.locator('.image-editor-preview img').getAttribute('src') === '/images/generated/menu-1.webp', 'Retry preview missing');
  await page.screenshot({ path: path.join(out, 'add-dish-image-preview.png') });
  checks.push({ name: 'Retry produces preview without saving a fake dish', passed: true });
  assert(!errors.length, errors.join('\n'));
  fs.writeFileSync(path.join(out, 'food-design-results.json'), JSON.stringify({ checks, pageErrors: errors, note: 'Image flow UI uses explicit mocks; live provider has a separate integration verification.' }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, pageErrors: errors }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
