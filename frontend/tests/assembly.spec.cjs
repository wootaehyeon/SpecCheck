const { test, expect } = require('@playwright/test');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

test('Canvas demo enforces board CPU cooler order and reverse removal order', async ({ page }, info) => {
  await page.goto(pathToFileURL(path.resolve(__dirname, '../pc_3d_assembly/index.html')).href);
  const card = name => page.locator('.part-card').filter({ hasText: name });
  await card('타워형 CPU 쿨러').click();
  await expect(page.locator('#toast')).toContainText('먼저 장착');
  await expect(page.locator('#progressText')).toHaveText('0 / 8');
  async function mount(name) {
    await card(name).click();
    // Read the rendered hit target; all state changes go through mouse clicks.
    const target = await page.evaluate(() => {
      const slot = clickable.find(x => x.kind === 'slot');
      const box = canvas.getBoundingClientRect();
      return {x:box.left+slot.x*box.width/canvas.width,y:box.top+slot.y*box.height/canvas.height};
    });
    await page.mouse.click(target.x, target.y);
    await expect(card(name)).toHaveClass(/mounted/);
  }
  await mount('MSI B650M');
  await card('타워형 CPU 쿨러').click();
  await expect(page.locator('#toast')).toContainText('CPU를 먼저');
  await mount('AMD Ryzen 5');
  await mount('타워형 CPU 쿨러');
  await expect(page.locator('#progressText')).toHaveText('3 / 8');
  await card('MSI B650M').click();
  await page.locator('#unmountBtn').click();
  await expect(page.locator('#toast')).toContainText('먼저 해제');
  await expect(page.locator('#progressText')).toHaveText('3 / 8');
  for (const name of ['타워형 CPU 쿨러', 'AMD Ryzen 5', 'MSI B650M']) {
    await card(name).click();
    await page.locator('#unmountBtn').click();
    await expect(card(name)).not.toHaveClass(/mounted/);
  }
  await expect(page.locator('#progressText')).toHaveText('0 / 8');
  await page.screenshot({ path: info.outputPath('assembly.png'), fullPage:true });
});
