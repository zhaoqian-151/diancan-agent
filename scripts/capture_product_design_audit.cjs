const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const out = path.join(__dirname, '../artifacts/product-design-audit');
fs.mkdirSync(out, { recursive: true });
function luminance(color) {
  const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}
const contrast = (a, b) => { const values = [luminance(a), luminance(b)].sort((a, b) => a - b); return Math.round((values[1] + .05) / (values[0] + .05) * 100) / 100; };
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: path.join(process.env.USERPROFILE, 'AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe') });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  await page.goto('http://127.0.0.1:3000/'); await page.waitForLoadState('networkidle');
  fs.writeFileSync(path.join(out, 'home-dom.txt'), await page.locator('body').ariaSnapshot());
  await page.screenshot({ path: path.join(out, '01-desktop-home.png'), animations: 'disabled' });
  const selectors = ['.dish-desc', '.assistant-welcome p', '.chat-suggestions button', '.ai-footnote', '.btn-add-cart', '.diet-filters label'];
  const colors = [];
  for (const selector of selectors) {
    const style = await page.locator(selector).first().evaluate(el => {
      const s = getComputedStyle(el); let current = el; let bg;
      while (current) { bg = getComputedStyle(current).backgroundColor; if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') break; current = current.parentElement; }
      const rect = el.getBoundingClientRect();
      return { color: s.color, background: bg || 'rgb(255, 255, 255)', fontSize: s.fontSize, height: rect.height, width: rect.width };
    });
    colors.push({ selector, ...style, contrast: contrast(style.color, style.background) });
  }
  const photos = page.locator('.dish-card .dish-visual img');
  const imageCount = await photos.count();
  for (const photo of await photos.all()) { await photo.scrollIntoViewIfNeeded(); await photo.evaluate(img => img.decode()); }
  await page.locator('.menu-grid').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(out, '02-dish-gallery.png'), animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 }); await page.evaluate(() => scrollTo(0, 0));
  await page.waitForFunction(() => document.querySelector('.app-sidebar').getBoundingClientRect().right <= 1);
  await page.screenshot({ path: path.join(out, '03-mobile-home.png'), animations: 'disabled' });
  const mobile = { input: await page.getByRole('textbox', { name: '向点餐助手提问' }).boundingBox(), viewportHeight: 844, docWidth: await page.evaluate(() => document.documentElement.scrollWidth) };
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto('http://127.0.0.1:3000/admin/menu'); await page.waitForLoadState('networkidle');
  const adminDom = await page.locator('body').ariaSnapshot();
  fs.writeFileSync(path.join(out, 'admin-dom.txt'), adminDom);
  if (!adminDom.includes('添加菜品')) throw new Error('Add dish control not present in current DOM');
  const add = page.getByRole('button', { name: '添加菜品' });
  if (await add.count() !== 1) throw new Error('Ambiguous add dish control');
  await add.click();
  const dialog = page.getByRole('dialog', { name: '添加菜品' }); await dialog.waitFor();
  fs.writeFileSync(path.join(out, 'add-dish-dom.txt'), await dialog.ariaSnapshot());
  await page.screenshot({ path: path.join(out, '04-add-dish.png'), animations: 'disabled' });
  const autoImage = await dialog.getByLabel('保存时自动生成缺失图片').isChecked();
  const result = { colors, mobile, imageCount, autoImage, note: 'Fresh screenshots from a separate authorized local Chromium session; no saved menu item, generated-image request, order or payment in this capture.' };
  fs.writeFileSync(path.join(out, 'measurements.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
