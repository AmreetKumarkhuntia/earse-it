import { test, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { copyFile, mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';

test('browser preview explains local processing and exposes help', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Make your subject/ })).toBeVisible();
  await page.getByRole('button', { name: 'Import your video' }).click();
  await expect(page.getByRole('alert')).toContainText('desktop');
  await page.getByRole('button', { name: 'Help', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Track both ways');
  await page.getByRole('button', { name: 'Close help' }).click();
  await page.getByRole('button', { name: 'Dismiss message' }).click();
  await page.screenshot({ path: 'test-results/workspace.png', fullPage: true });
});

test('real CPU worker: import, select, track, correct, undo, save, export', async ({ page }) => {
  test.skip(process.env.ERASE_IT_E2E !== '1', 'Requires local Python runtime and downloaded Tiny model');
  const root = process.cwd();
  const directory = path.join(root, '.cache/e2e', crypto.randomUUID());
  const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const source = path.join(directory, 'subject.mkv');
  const output = path.join(directory, 'subject-cutout.mov');
  const projectFile = path.join(directory, 'subject.cutout');
  await mkdir(path.join(directory, 'models'), { recursive: true });
  await copyFile(path.join(root, '.cache/inference/models/sam2.1_hiera_tiny.pt'), path.join(directory, 'models/sam2.1_hiera_tiny.pt'));
  execFileSync(process.env.ERASE_IT_FFMPEG ?? 'ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x202e3a:s=256x160:r=3:d=1', '-vf', 'drawbox=x=75:y=35:w=100:h=95:color=0xd7a028:t=fill', '-c:v', 'ffv1', source]);
  const child = spawn(python, ['-m', 'erase_it', '--data-dir', directory], { cwd: root, stdio: ['pipe', 'pipe', 'pipe'] });
  let handler = 0;
  let stderr = '';
  child.stderr.on('data', value => { stderr += value.toString(); });
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => {
    const payload = JSON.parse(line);
    void page.evaluate(({ handler, payload }) => {
      const callbacks = (window as unknown as { __callbacks: Record<number, (value: unknown) => void> }).__callbacks;
      callbacks[handler]?.({ event: 'worker-message', id: 1, payload });
    }, { handler, payload }).catch(() => undefined);
  });
  await page.exposeFunction('__testInvoke', async (command: string, args: Record<string, unknown>) => {
    if (command === 'plugin:event|listen') { handler = args.handler as number; return 1; }
    if (command === 'plugin:event|unlisten') return;
    if (command === 'worker_request') { child.stdin.write(JSON.stringify(args.request) + '\n'); return; }
    if (command === 'plugin:dialog|open') return source;
    if (command === 'plugin:dialog|save') {
      const options = args.options as { defaultPath?: string };
      return options.defaultPath?.endsWith('.cutout') ? projectFile : output;
    }
    throw new Error(`Unexpected native call: ${command}`);
  });
  await page.addInitScript(() => {
    const scope = window as unknown as Record<string, unknown>;
    scope.isTauri = true;
    const callbacks: Record<number, (value: unknown) => void> = {};
    let next = 1;
    scope.__callbacks = callbacks;
    scope.__TAURI_INTERNALS__ = {
      invoke: (command: string, args: unknown) => (scope.__testInvoke as (command: string, args: unknown) => Promise<unknown>)(command, args),
      transformCallback: (callback: (value: unknown) => void) => { const id = next++; callbacks[id] = callback; return id; },
      convertFileSrc: (file: string) => `/__test_assets?file=${encodeURIComponent(file)}`,
    };
  });
  await page.route('**/__test_assets?**', async route => {
    const file = path.resolve(new URL(route.request().url()).searchParams.get('file')!);
    if (!file.startsWith(directory + path.sep)) return route.abort();
    await route.fulfill({ body: await readFile(file), contentType: file.endsWith('.jpg') ? 'image/jpeg' : file.endsWith('.webm') ? 'video/webm' : 'image/png' });
  });
  try {
    await page.goto('/');
    await expect(page.locator('.statusbar')).toContainText('Ready');
    await page.getByRole('button', { name: 'Import your video' }).click();
    await expect(page.locator('.media-card')).toContainText('subject');
    await expect(page.locator('.frame-image')).toBeVisible();
    const viewer = await page.locator('.viewer').boundingBox();
    if (!viewer) throw new Error('No viewer');
    await page.mouse.click(viewer.x + viewer.width / 2, viewer.y + viewer.height / 2);
    await expect(page.locator('.keyframes button')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Track both ways' })).toBeEnabled();
    await page.getByRole('button', { name: 'Track both ways' }).click();
    await expect(page.getByRole('button', { name: 'Export cutout' })).toBeEnabled({ timeout: 60_000 });
    await page.getByRole('button', { name: 'cutout', exact: true }).click();
    await expect(page.locator('.frame-image')).toHaveAttribute('src', /-cutout-00000000\.png/);
    await expect(page.locator('.frame-image')).toHaveJSProperty('complete', true);
    await page.screenshot({ path: 'test-results/cutout.png', fullPage: true });
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.locator('.notice[role="status"]')).toContainText('Project saved');
    await page.getByRole('button', { name: 'Export cutout' }).click();
    await expect(page.locator('.notice[role="status"]')).toContainText('Export saved');
    const bytes = await readFile(output);
    expect(bytes.length).toBeGreaterThan(1000);
    await page.getByRole('button', { name: 'Next frame', exact: true }).click();
    await expect(page.locator('.frame-image')).toHaveAttribute('alt', /Frame 2/);
    await page.mouse.click(viewer.x + viewer.width * .5, viewer.y + viewer.height * .5);
    await expect(page.locator('.keyframes button')).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'Export cutout' })).toBeDisabled();
    await page.getByTitle('Undo selection', { exact: true }).click();
    await expect(page.locator('.keyframes button')).toHaveCount(1);
  } finally {
    child.stdin.end();
    await new Promise<void>(resolve => { child.once('exit', () => resolve()); setTimeout(() => { child.kill(); resolve(); }, 3000).unref(); });
    if (stderr.includes('Traceback')) console.error(stderr);
  }
});
