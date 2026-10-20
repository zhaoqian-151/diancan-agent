const fs = require('node:fs');
const path = require('node:path');
let sharp;
try { sharp = require('sharp'); } catch { sharp = require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp')); }
const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/design/image-prompts.json'), 'utf8'));
const out = path.join(root, 'ui/public/images/generated');
fs.mkdirSync(out, { recursive: true });
(async () => {
  for (const asset of manifest.images) {
    const filename = asset.id + '.webp';
    await sharp(asset.source).resize({ width: asset.id === 'hero-feast' ? 1600 : 1000, withoutEnlargement: true }).webp({ quality: 86 }).toFile(path.join(out, filename));
    console.log(filename + ' ' + fs.statSync(path.join(out, filename)).size + ' bytes');
  }
})().catch(e => { console.error(e); process.exit(1); });
