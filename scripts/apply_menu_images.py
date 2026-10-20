"""Associate generated local assets with existing dishes; preserve merchant photos."""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import db_tool

manifest = json.loads((ROOT / 'artifacts/design/image-prompts.json').read_text(encoding='utf-8'))
assets = [entry for entry in manifest['images'] if entry.get('dish_id')]
with db_tool.db_cursor() as cursor:
    cursor.execute('SELECT id, dish_name, image_url FROM menu_items ORDER BY id')
    before = cursor.fetchall()
backup = ROOT / 'artifacts/design' / f'menu-images-before-{datetime.now():%Y%m%d-%H%M%S}.json'
backup.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
changed = 0
with db_tool.db_cursor(commit=True) as cursor:
    for asset in assets:
        local = ROOT / 'ui/public/images/generated' / f'{asset["id"]}.webp'
        if not local.is_file():
            raise RuntimeError(f'Missing asset {local.name}')
        cursor.execute(
            'UPDATE menu_items SET image_url=%s, updated_at=NOW() '
            'WHERE id=%s AND dish_name=%s AND (image_url IS NULL OR image_url=%s OR image_url LIKE %s)',
            (f'/images/generated/{local.name}', asset['dish_id'], asset['dish_name'], '', '%text_to_image%'))
        changed += cursor.rowcount
print(json.dumps({'updated_menu_images': changed, 'backup': str(backup)}, ensure_ascii=True))
