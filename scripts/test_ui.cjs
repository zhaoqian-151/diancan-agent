/* Browser acceptance checks. Uses the installed Playwright or the bundled runtime. */
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('../ui/node_modules/playwright'); }
catch { playwright = require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const base = process.env.DIANCAN_UI_URL || 'http://127.0.0.1:3000';
const out = path.join(__dirname, '../artifacts/review');
fs.mkdirSync(out, { recursive: true });
const assert = (condition, message) => { if (!condition) throw new Error(message); };
(async () => {
  const browser = await playwright.chromium.launch({ headless: true, executablePath: process.env.DIANCAN_CHROMIUM || path.join(process.env.USERPROFILE, 'AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe') });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [], checks = [], layoutFailures = [];
  page.on('pageerror', e => errors.push(e.message));
  const routes = ['/', '/admin', '/orders', '/admin/orders', '/admin/menu', '/admin/tables', '/admin/inventory', '/admin/members', '/admin/reports', '/kitchen'];
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1080 });
    for (const route of routes) {
      await page.goto(base + route);
      await page.waitForLoadState('networkidle');
      const overflow = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, width: innerWidth }));
      if (overflow.doc > overflow.width + 1) layoutFailures.push(`Horizontal overflow ${route} at ${width}: ${JSON.stringify(overflow)}`);
      assert(!(await page.locator('.load-error').count()), `API error on ${route}`);
      if (route === '/') {
        const dishPhotos = page.locator('.dish-card .dish-visual img');
        assert(await dishPhotos.count() === (await page.locator('.dish-card').count()), 'Missing menu images');
        for (const photo of await dishPhotos.all()) {
          await photo.scrollIntoViewIfNeeded();
          await photo.evaluate(img => img.decode());
          assert(await photo.evaluate(img => img.naturalWidth > 200), 'Menu image did not load');
        }
        await page.evaluate(() => scrollTo(0, 0));
      }
      if ((route === '/' || route === '/admin') && (width === 1440 || width === 390)) await page.screenshot({ path: path.join(out, `${route === '/' ? 'dining' : 'dashboard'}-${width}.png`), fullPage: true });
      checks.push({ route, width, passed: true });
    }
  }
  assert(!layoutFailures.length, layoutFailures.join('\n'));
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto(base); await page.waitForLoadState('networkidle');
  const total = await page.locator('.dish-card').count();
  const menuCount = (await (await context.request.get(base + '/api/menu/list')).json()).total;
  assert(total === menuCount && total > 0, `Expected ${menuCount} database dishes; received ${total}`);
  await page.getByRole('textbox', { name: '搜索菜品' }).fill('宫保鸡丁');
  assert(await page.locator('.dish-card').count() === 1, 'Menu search failed');
  await page.getByRole('button', { name: '重置筛选' }).click();
  await page.getByLabel('只看素食').check();
  assert(await page.locator('.dish-card').count() > 0, 'No vegetarian dishes shown');
  assert(await page.locator('.dish-card .dish-tag.veggie').count() === await page.locator('.dish-card').count(), 'Vegetarian filter failed');
  await page.getByRole('button', { name: '重置筛选' }).click();
  await page.locator('.dish-card:not(.unavailable) .btn-add-cart').first().click();
  await page.waitForFunction(() => document.querySelector('.assistant-cart-summary.has-cart'));
  await page.getByRole('button', { name: '查看购物车' }).click();
  await page.locator('.cart-drawer').waitFor();
  await page.getByRole('button', { name: '去结算', exact: true }).click();
  await page.getByRole('dialog', { name: '确认下单' }).waitFor();
  assert(await page.getByText('在线支付尚未接入。提交后订单保留为待支付').count() > 0, 'Missing honest payment notice');
  await page.getByRole('button', { name: '取消', exact: true }).last().click();
  await page.locator('.qty-ctrl button').first().click();
  await page.waitForFunction(() => document.querySelector('.cart-drawer')?.textContent.includes('购物车是空的'));
  await page.keyboard.press('Escape');
  checks.push({ interaction: 'search, vegetarian filter, cart, checkout notice and remove', passed: true });
  await page.route('**/api/chat', route => route.fulfill({ json: { response: '<img src=x onerror="window.injected=true"> **测试回复**', menu_ids: [], session_id: 'acceptance-mock' } }));
  await page.getByRole('textbox', { name: '向点餐助手提问' }).fill('<script>window.injected=true</script>');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.chat-bubble.assistant').length === 1);
  assert(!(await page.evaluate(() => window.injected)), 'AI content executed as HTML');
  assert(await page.locator('.chat-bubble img, .chat-bubble script').count() === 0, 'Unsafe HTML rendered');
  checks.push({ interaction: 'AI text escaping (mock response)', passed: true });
  await page.unroute('**/api/chat');
  await page.route('**/api/menu/list', route => route.fulfill({ status: 503, json: { detail: '验收测试：菜单暂不可用' } }));
  await page.reload(); await page.waitForLoadState('networkidle');
  assert(await page.getByRole('alert').filter({ hasText: '暂时无法获取数据' }).count() > 0, 'Failure incorrectly rendered as empty menu');
  await page.unroute('**/api/menu/list');
  await page.getByRole('button', { name: '重新加载', exact: true }).click();
  await page.waitForFunction(count => document.querySelectorAll('.dish-card').length === count, menuCount);
  checks.push({ interaction: 'API failure and successful retry', passed: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航' }).click();
  await page.getByRole('link', { name: '餐厅经营', exact: true }).click();
  await page.waitForURL(base + '/admin');
  assert(!(await page.locator('.app-shell').getAttribute('class')).includes('nav-open'), 'Mobile menu did not close');
  checks.push({ interaction: 'mobile navigation', passed: true });
  assert(!errors.length, `Browser errors: ${errors.join('; ')}`);
  fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify({ checks, pageErrors: errors }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, pageErrors: errors, screenshots: out }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
