"""端到端联调：全部请求走前端开发服务器(3000)，经 vite 代理转发到后端(8000)。

这条链路是：浏览器 -> vite(3000) -> 代理 rewrite 去掉 /api -> FastAPI(8000)
        -> MySQL / Pinecone / 高德 / 大模型
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FRONT = 'http://localhost:3000'
BACK = 'http://127.0.0.1:8000'

# vite 只监听 localhost（IPv6 ::1），且 SPA 回退要求请求接受 HTML，
# 所以这里必须带上浏览器会发的请求头，否则 GET / 会被当成找不到
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


def fetch(url, payload=None, method=None, timeout=180, raw=False):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in BROWSER_HEADERS.items():
        request.add_header(key, value)
    if data:
        request.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8', 'replace')
            return response.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace')[:300]
    except Exception as exc:  # noqa: BLE001
        return None, f'{type(exc).__name__}: {exc}'


def section(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)


section('1) 首页 HTML（前端开发服务器）')
status, html = fetch(FRONT + '/', raw=True)
print(f'  状态码 {status}  HTML 长度 {len(html) if isinstance(html, str) else "?"}')
if isinstance(html, str):
    print(f"  标题      : {re.search(r'<title>(.*?)</title>', html).group(1)}")
    print(f"  挂载点    : {'有 <div id=\"app\">' if 'id=\"app\"' in html else '缺少 #app'}")
    print(f"  入口脚本  : {re.search(r'src=\"([^\"]*main[^\"]*)\"', html).group(1)}")
    print(f"  vite 客户端: {'已注入' if '/@vite/client' in html else '未注入'}")

section('2) 入口模块能否被编译并下发')
status, body = fetch(FRONT + '/src/main.js', raw=True)
print(f'  状态码 {status}  长度 {len(body) if isinstance(body, str) else "?"}')
if isinstance(body, str) and status == 200:
    print(f"  内容前 120 字: {body[:120]}")

section('3) 走代理的 GET /api/menu/list')
status, body = fetch(FRONT + '/api/menu/list')
print(f'  状态码 {status}  共 {body.get("total")} 道菜  分类 {body.get("categories")}')
for item in body.get('menu_items', []):
    print(f"    {item['id']}  {item['dish_name']:<8} {item['formatted_price']:>8} "
          f"{item['spice_text']:<4} 素食={item['is_vegetarian']}")

section('4) 走代理的 GET /api/health')
status, body = fetch(FRONT + '/api/health')
print(f'  状态码 {status}  status={body.get("status")}  '
      f'MySQL {body["checks"]["mysql"]["version"]}')

section('5) 走代理的 POST /api/delivery（模拟前端传字符串 travel_mode）')
for address, mode in [('重庆市大渡口区茄子溪', '2'), ('重庆市渝中区解放碑', '3')]:
    status, body = fetch(FRONT + '/api/delivery',
                         {'address': address, 'travel_mode': mode})
    print(f"\n  {address}  mode={mode}")
    print(f'    状态码 {status}  in_range={body["in_range"]}  '
          f'distance={body["distance"]}  duration={body["duration"]}')
    print(f'    {body["message"]}')

section('6) 走代理的 POST /api/chat（三个工具 + 多轮）')
session_id = None
for label, question in [
    ('餐厅信息查询', '你们店在哪里？营业到几点？'),
    ('智能菜品推荐', '我不太能吃辣，有什么推荐？'),
    ('配送范围检查', '能送到大渡口区茄子溪吗？'),
]:
    payload = {'query': question}
    if session_id:
        payload['session_id'] = session_id
    started = time.time()
    status, body = fetch(FRONT + '/api/chat', payload)
    session_id = body.get('session_id', session_id)
    print(f'\n  【{label}】{question}')
    print(f'    状态码 {status}  类型 {body["type"]}  工具 {body["tool_calls"]}  '
          f'耗时 {body["elapsed_ms"]}ms')
    if body.get('menu_ids'):
        print(f'    前端高亮菜品: {body["menu_ids"]}')
    print(f'    回复：{body["response"]}')

section('7) 多轮追问（同一 session_id）')
status, body = fetch(FRONT + '/api/chat',
                     {'query': '那你们几点关门？', 'session_id': session_id})
print(f'  状态码 {status}  历史轮数 {body.get("history_turns")}  工具 {body["tool_calls"]}')
print(f'  回复：{body["response"]}')

section('8) 代理与直连结果一致性')
status_a, a = fetch(FRONT + '/api/menu/list')
status_b, b = fetch(BACK + '/menu/list')
same = a.get('menu_items') == b.get('menu_items')
print(f'  经代理(3000) {status_a}  vs  直连(8000) {status_b}  数据一致: {same}')

print()
print('端到端联调完成')