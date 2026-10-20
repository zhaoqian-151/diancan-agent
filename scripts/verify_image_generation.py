"""Live verification of the website's image API, without creating a menu item."""
import json
import time
from pathlib import Path
import httpx

with httpx.Client(base_url='http://127.0.0.1:3000/api', timeout=30, trust_env=False) as client:
    response = client.post('/admin/menu/image-jobs', json={
        'dish_name': '香菇滑鸡', 'category': '粤菜', 'main_ingredients': '鸡肉,香菇,姜,葱',
        'description': '鲜嫩鸡肉搭配香菇，酱汁鲜香', 'cooking_method': '清蒸', 'is_vegetarian': False})
    response.raise_for_status()
    job = response.json()
    print(json.dumps({'job_id': job['job_id'], 'status': job['status']}), flush=True)
    deadline = time.monotonic() + 240
    while job['status'] not in ('succeeded', 'failed') and time.monotonic() < deadline:
        time.sleep(2)
        response = client.get('/admin/menu/image-jobs/' + job['job_id'])
        response.raise_for_status()
        job = response.json()
    assert job['status'] == 'succeeded', job
    image = client.get('http://127.0.0.1:3000' + job['image_url'])
    image.raise_for_status()
    assert image.headers['content-type'].startswith('image/') and len(image.content) > 10000
    out = Path(__file__).resolve().parents[1] / 'artifacts/design'
    (out / 'live-generation-result.json').write_text(json.dumps({
        'passed': True, 'job': job, 'image_bytes': len(image.content),
        'note': 'Real provider call; image persisted locally; no menu item or order created'}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'image_url': job['image_url'], 'image_bytes': len(image.content)}), flush=True)
