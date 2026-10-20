"""接口联调：逐个打 FastAPI 的四个接口，并模拟前端的取值方式。"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:8000'


def call(method: str, path: str, payload=None, timeout=120):
    """返回 (状态码, 响应体)。"""
    url = BASE + path
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data:
        request.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body
    except Exception as exc:  # noqa: BLE001
        return None, f'{type(exc).__name__}: {exc}'


def section(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)


section('1) GET /  服务简介')
status, body = call('GET', '/')
print(f'  状态码 {status}')
print(f'  {json.dumps(body, ensure_ascii=False)}')

section('2) GET /health  健康检查')
status, body = call('GET', '/health')
print(f'  状态码 {status}  status={body.get("status")}')
print(f'  MySQL: {body["checks"]["mysql"]}')
print(f'  会话  : {body["sessions"]}')

section('3) GET /health?deep=true  含外部依赖探测')
status, body = call('GET', '/health?deep=true')
print(f'  状态码 {status}  status={body.get("status")}')
for name, value in body['checks'].items():
    ok = value.get('ok', True)
    print(f'  {name:<10} ok={ok}')

section('4) GET /menu/list  菜品列表')
status, body = call('GET', '/menu/list')
print(f'  状态码 {status}  共 {body["total"]} 道菜  分类 {body["categories"]}')
first = body['menu_items'][0]
print(f'  字段: {sorted(first.keys())}')
for item in body['menu_items']:
    print(f"    {item['id']}  {item['dish_name']:<8} {item['formatted_price']:>8}  "
          f"{item['spice_text']:<4} 素食={item['is_vegetarian']}")

section('5) POST /delivery  配送查询')
for address, mode in [('重庆市大渡口区茄子溪', 3),
                      ('重庆市大渡口区九宫庙', 2),
                      ('重庆市渝中区解放碑', 3),
                      ('不存在的地址乱码xyz', 3)]:
    status, body = call('POST', '/delivery', {'address': address, 'travel_mode': mode})
    print(f'\n  查询 {address}（travel_mode={mode}）状态码 {status}')
    print(f"    success={body['success']} in_range={body['in_range']} "
          f"distance={body['distance']} duration={body['duration']} "
          f"low_confidence={body['low_confidence']}")
    print(f"    {body['message']}")
    # 模拟 App.vue 的渲染逻辑
    if body['distance']:
        print(f"    前端渲染 -> 距离 {body['distance']:.2f} 公里 / "
              f"{body['duration'] // 60} 分钟 {body['duration'] % 60} 秒 / "
              f"提示类型 {'success' if body['in_range'] else 'warning'}")

section('6) POST /chat  智能对话（三个工具各测一次）')
CHATS = [
    ('常规咨询', '你们店在哪儿？几点开门？'),
    ('菜品推荐', '我想吃点辣的，有什么推荐吗？'),
    ('配送检查', '能送到重庆市大渡口区茄子溪吗？'),
]
session_id = None
for label, question in CHATS:
    started = time.time()
    payload = {'query': question}
    if session_id:
        payload['session_id'] = session_id
    status, body = call('POST', '/chat', payload)
    session_id = body.get('session_id') if isinstance(body, dict) else None
    print(f'\n  【{label}】{question}')
    print(f'    状态码 {status}  类型 {body["type"]}  工具 {body["tool_calls"]}  '
          f'耗时 {body["elapsed_ms"]}ms（实测 {int((time.time() - started) * 1000)}ms）')
    print(f'    session_id {session_id}')
    # 模拟 App.vue 的渲染分支
    if body.get('recommendation'):
        print(f'    [前端走 recommendation 分支] 高亮菜品 {body["menu_ids"]}')
    elif body.get('response'):
        print('    [前端走 response 分支]')
    print(f'    回复：{body["response"]}')

section('7) 多轮对话（同一 session_id 追问）')
status, body = call('POST', '/chat', {'query': '那这个能送到大渡口区九宫庙吗？',
                                      'session_id': session_id})
print(f'  状态码 {status}  类型 {body["type"]}  工具 {body["tool_calls"]}  '
      f'历史轮数 {body.get("history_turns")}')
print(f'  回复：{body["response"]}')

section('8) 异常输入')
status, body = call('POST', '/chat', {'query': '   '})
print(f'  空 query      -> 状态码 {status}  {body}')
status, body = call('POST', '/delivery', {'address': ''})
print(f'  空 address    -> 状态码 {status}  {body}')
status, body = call('POST', '/chat', {'wrong_field': '你好'})
print(f'  缺字段        -> 状态码 {status}  {str(body)[:120]}')

section('9) DELETE /session/{id}  清空会话')
status, body = call('DELETE', f'/session/{session_id}')
print(f'  状态码 {status}  {body}')
status, body = call('POST', '/chat', {'query': '刚才聊了什么？', 'session_id': session_id})
print(f'  清空后追问 -> 历史轮数 {body.get("history_turns")}（应为 0）')
print(f'  回复：{body["response"]}')

print()
print('接口联调完成')