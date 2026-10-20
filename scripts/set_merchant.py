"""把商户地址通过高德地理编码转成经纬度，并写回 .env。"""
import os
import re
import urllib.parse
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

KEY = None
with open(ENV_PATH, encoding='utf-8') as fh:
    for line in fh:
        if line.startswith('AMAP_API_KEY='):
            KEY = line.split('=', 1)[1].strip()
if not KEY:
    raise SystemExit('未在 .env 中找到 AMAP_API_KEY')

ADDRESS = '重庆市大渡口区兴海路204号'
MERCHANT_NAME = '友邻便利店（大渡口区兴海路204号）'

url = 'https://restapi.amap.com/v3/geocode/geo?' + urllib.parse.urlencode({
    'key': KEY, 'address': ADDRESS, 'city': '重庆', 'output': 'JSON',
})
data = urllib.request.urlopen(url, timeout=30).read().decode('utf-8', 'replace')
import json  # noqa: E402
result = json.loads(data)

print('status =', result.get('status'), 'info =', result.get('info'), 'count =', result.get('count'))
if result.get('status') != '1' or not result.get('geocodes'):
    raise SystemExit('地理编码失败：' + data[:300])

best = result['geocodes'][0]
lng, lat = best['location'].split(',')
print('匹配地址 :', best.get('formatted_address'))
print('经纬度   :', lng, lat)
print('所在区   :', best.get('district'), best.get('city'))
for alt in result['geocodes'][1:4]:
    print('  备选   :', alt.get('formatted_address'), alt.get('location'))

# 逆地理编码复核
rev_url = 'https://restapi.amap.com/v3/geocode/regeo?' + urllib.parse.urlencode({
    'key': KEY, 'location': f'{lng},{lat}', 'output': 'JSON',
})
rev = json.loads(urllib.request.urlopen(rev_url, timeout=30).read().decode('utf-8', 'replace'))
regeo = rev.get('regeocode') or {}
print('逆地理复核:', regeo.get('formatted_address'))

print()
print('经纬度相近性检查（该点在重庆，若纬度约 29.4 / 经度约 106.4 则正确）:')
print(f'  lon={float(lng):.6f}  lat={float(lat):.6f}')

# 写回 .env
with open(ENV_PATH, encoding='utf-8') as fh:
    content = fh.read()

content = re.sub(r'^MERCHANT_LONGITUDE=.*$', f'MERCHANT_LONGITUDE={lng}', content, flags=re.M)
content = re.sub(r'^MERCHANT_LATITUDE=.*$', f'MERCHANT_LATITUDE={lat}', content, flags=re.M)
content = re.sub(r'^MERCHANT_NAME=.*$', f'MERCHANT_NAME={MERCHANT_NAME}', content, flags=re.M)
content = content.replace(
    '# 注：原配置里武汉、北京两组经纬度重复定义，后者覆盖前者。\n'
    '#     菜单脚本 menu.sql 中历史订单地址均为北京（回龙观/中关村），故保留北京坐标。\n',
    '# 由高德地理编码生成，来源地址：' + ADDRESS + '\n',
)

with open(ENV_PATH, 'w', encoding='utf-8') as fh:
    fh.write(content)

print()
print('已写回 .env：')
with open(ENV_PATH, encoding='utf-8') as fh:
    for line in fh:
        if line.startswith(('MERCHANT_', 'DELIVERY_RADIUS', 'DEFAULT_PATH_MODE')):
            print('  ' + line.rstrip())