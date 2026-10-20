"""最终整体核验：后端四个功能、前端代理、外部依赖。"""

import json
import sys
import urllib.error
import urllib.request

BACK = 'http://127.0.0.1:8000'
FRONT = 'http://localhost:3000'


def get(url, accept='application/json'):
    request = urllib.request.Request(url)
    request.add_header('Accept', accept)
    request.add_header('User-Agent', 'Mozilla/5.0')
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode('utf-8', 'replace')
            return response.status, (json.loads(body) if accept == 'application/json' else body)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')[:200]
    except Exception as exc:  # noqa: BLE001
        return None, f'{type(exc).__name__}: {exc}'


print('=== 后端 /health?deep=true ===')
status, body = get(BACK + '/health?deep=true')
if isinstance(body, dict):
    print(f"  状态码 {status}   status = {body['status']}")
    for name, value in body['checks'].items():
        print(f"    {name:<10} ok={value.get('ok')}")
else:
    print(f'  失败: {body}')

print()
print('=== 四个核心功能（经前端代理）===')
checks = [
    ('智能菜品推荐与咨询', 'POST', '/api/chat', {'query': '推荐个不辣的菜'}),
    ('餐厅信息查询', 'POST', '/api/chat', {'query': '你们店在哪，几点营业'}),
    ('配送范围检查', 'POST', '/api/delivery', {'address': '重庆市大渡口区茄子溪', 'travel_mode': '2'}),
    ('用户对话交互', 'POST', '/api/chat', {'query': '你好'}),
]
for label, method, path, payload in checks:
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(FRONT + path, data=data, method=method)
    request.add_header('Content-Type', 'application/json')
    request.add_header('Accept', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode('utf-8'))
        if 'tool_calls' in body:
            detail = f"工具 {body['tool_calls']}  类型 {body['type']}  {body['elapsed_ms']}ms"
        else:
            detail = f"in_range={body['in_range']}  {body['distance']} 公里  {body['duration']} 秒"
        print(f"  [OK] {label:<18} {detail}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [失败] {label:<18} {type(exc).__name__}: {exc}")

print()
print('=== 菜品列表接口 ===')
status, body = get(BACK + '/menu/list')
print(f"  状态码 {status}  {body['total']} 道菜  分类 {body['categories']}")
print()
print('全部核验完成')