/* Read-only admin UI checks against the running API. Never changes business records. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const out = path.join(__dirname, '../artifacts/admin-design');
const base = process.env.DIANCAN_UI_URL || 'http://127.0.0.1:3000';
fs.mkdirSync(out, { recursive: true });
const assert = (condition, message) => { if (!condition) throw new Error(message); };
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: path.join(process.env.USERPROFILE, 'AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe') });
  const context = await browser.newContext({ viewport: { width:1440, height:1080 } });
  const page = await context.newPage();
  const errors = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  const visit = async route => { await page.goto(base + route); await page.waitForLoadState('networkidle'); };
  const check = (ok, description) => { assert(ok, description); checks.push(description); };
  try {
    const routes = ['/admin','/admin/orders','/admin/menu','/admin/inventory','/admin/tables','/admin/members','/admin/reports','/kitchen'];
    for (const width of [1440,768,390,320]) {
      await page.setViewportSize({ width,height:width < 500 ? 844 : 1080 });
      for (const route of routes) {
        await visit(route);
        const layout = await page.evaluate(() => ({ width:innerWidth,scroll:document.documentElement.scrollWidth }));
        check(layout.scroll <= layout.width + 1, `${route} at ${width}: no page overflow`);
        check(await page.locator('.admin-mode .admin-page-heading h1').count() === 1 && !(await page.locator('.load-error').count()), `${route} at ${width}: new header and API loaded`);
        if (width === 1440 || width === 390) {
          for (const photo of await page.locator('.admin-menu-desktop:visible .admin-dish-thumb img, .admin-menu-mobile:visible .admin-mobile-dish-photo img').all()) { await photo.scrollIntoViewIfNeeded(); await photo.evaluate(img => img.decode()); }
          await page.evaluate(() => scrollTo(0,0));
          await page.screenshot({ path:path.join(out,`${route.slice(1).replaceAll('/','-')}-${width}.png`),fullPage:true });
        }
      }
    }
    await page.setViewportSize({ width:1440,height:1080 });
    const get = async endpoint => { const response = await context.request.get(base+'/api'+endpoint); assert(response.ok(), endpoint); return response.json(); };
    const menu = (await get('/menu/list')).menu_items;
    await visit('/admin/menu');
    check(await page.locator('.admin-table tbody tr:has(.admin-dish-name)').count() === menu.length,'Menu count matches database');
    for (const photo of await page.locator('.admin-dish-thumb img').all()) { await photo.scrollIntoViewIfNeeded(); await photo.evaluate(img => img.decode()); }
    check(await page.locator('.admin-dish-thumb img').count() === menu.length,'All menu rows have working dish photos');
    await page.getByRole('textbox',{name:'搜索菜品',exact:true}).fill(menu[0].dish_name);
    check(await page.locator('.admin-dish-name').count() === menu.filter(d=>`${d.dish_name} ${d.main_ingredients || ''}`.includes(menu[0].dish_name)).length,'Dish keyword search');
    await page.getByRole('textbox',{name:'搜索菜品',exact:true}).fill('');
    await page.getByLabel('菜品销售状态').selectOption('off');
    check(await page.locator('.admin-dish-name').count() === menu.filter(d=>!d.is_available).length,'Dish availability filter');
    await page.getByLabel('菜品销售状态').selectOption('all');
    await page.getByRole('button',{name:'添加菜品'}).click();
    check(await page.getByRole('checkbox',{name:'保存时自动生成缺失图片'}).isChecked(),'New dish keeps automatic image generation enabled');
    await page.getByRole('button',{name:'取消',exact:true}).click();
    const inventory = await get('/admin/inventory');
    await visit('/admin/inventory');
    await page.getByLabel('库存状态').selectOption('low');
    check(await page.locator('.inv-row').count() === inventory.ingredients.filter(i=>i.low).length,'Low-stock filter matches API');
    await page.getByLabel('库存状态').selectOption('all');
    if (inventory.ingredients.length) {
      await page.getByRole('textbox',{name:'搜索原料'}).fill(inventory.ingredients[0].name);
      check(await page.locator('.inv-row').count()>0,'Inventory search');
      await page.getByRole('button',{name:'补货',exact:true}).first().click();
      check(await page.getByRole('dialog',{name:'原料补货'}).isVisible(),'Restock form still available');
      await page.getByRole('button',{name:'取消',exact:true}).click();
    }
    const tables = (await get('/admin/tables')).tables;
    await visit('/admin/tables');
    await page.locator('.admin-tab button').filter({hasText:'空闲'}).click();
    check(await page.locator('.table-card').count() === tables.filter(t=>t.status===0).length,'Free-table filter matches API');
    const orders = (await get('/admin/orders?limit=200')).orders;
    await visit('/admin/orders');
    for (const order of orders.filter(o=>o.payment_status!==1 && [1,2].includes(o.status))) {
      const card = page.locator('.order-card').filter({hasText:order.order_no});
      check(await card.locator('.order-footer button').count()===0,'Unpaid historical order offers no forbidden progress action');
    }
    for (const status of [0,1,2,3,4]) {
      const button = page.locator('.admin-tab button').nth(status+1);
      check(Number(await button.locator('.tab-count').textContent()) === orders.filter(o=>o.status===status).length,`Order status ${status} count matches API`);
      await button.click();
      check(await page.locator('.order-card').count() === orders.filter(o=>o.status===status).length,`Order status ${status} filter`);
    }
    if (orders.length) {
      await page.locator('.admin-tab button').first().click();
      await page.getByRole('textbox',{name:'搜索订单',exact:true}).fill(orders[0].order_no);
      check(await page.locator('.order-card').count() === 1,'Order number search');
      check(await page.locator('.admin-order-line').count() === orders[0].items.length,'Actual order dish details rendered');
    }
    await visit('/admin/members');
    await page.getByRole('textbox',{name:'搜索会员'}).fill('NO_MATCH_ADMIN_DESIGN');
    await Promise.all([page.waitForResponse(r=>r.url().includes('/api/admin/members') && r.status()===200),page.getByRole('button',{name:'搜索会员',exact:true}).click()]);
    await page.waitForTimeout(150);
    check(await page.locator('.member-card').count()===0 && (await page.locator('.empty-state').textContent()).includes('没有符合'),'Member search empty state');
    const kitchen = await get('/admin/kitchen');
    await visit('/kitchen');
    check(await page.locator('.kitchen-col').count()===kitchen.stations.length,'Kitchen keeps all actual station columns visible');
    await page.setViewportSize({width:390,height:844});
    await visit('/admin');
    await page.getByRole('button',{name:'打开导航'}).click();
    await page.locator('.sidebar-link').filter({hasText:'菜品管理'}).click();
    await page.waitForURL('**/admin/menu');
    await page.waitForFunction(()=>!document.querySelector('.app-shell').classList.contains('nav-open'));
    check(new URL(page.url()).pathname==='/admin/menu' && !(await page.locator('.app-shell').getAttribute('class')).includes('nav-open'),'Mobile admin navigation');
    await visit('/');
    check(await page.locator('.dining-mode').count()===1 && await page.locator('.admin-mode').count()===0,'Customer design remains isolated');
    check(!errors.length,'No browser runtime errors');
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({passed:checks.length,checks,pageErrors:errors},null,2));
    console.log(JSON.stringify({passed:checks.length,pageErrors:errors,screenshots:out}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1)});
