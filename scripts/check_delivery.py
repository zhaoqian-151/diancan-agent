"""以新商户坐标为起点，验证配送范围计算的可行性。"""
import json
import os
import urllib.parse
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

cfg = {}
with open(ENV_PATH, encoding='utf-8') as fh:
    for line in fh:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip()

KEY = cfg['AMAP_API_KEY']
ORIGIN = f"{cfg['MERCHANT_LONGITUDE']},{cfg['MERCHANT_LATITUDE']}"
RADIUS = int(cfg['DELIVERY_RADIUS'])

print(f"商户坐标: {ORIGIN}   配送半径: {RADIUS} 米\n")

# 1-步行 2-骑行 3-驾车
MODE_PATH = {1: 'walking', 2: 'riding', 3: 'driving'}


def get(path, params):
    params = dict(params, key=KEY, output='JSON')
    url = 'https://restapi.amap.com/v3/' + path + '?' + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, timeout=30).read().decode('utf-8', 'replace'))


def geocode(address):
    r = get('geocode/geo', {'address': address, 'city': '重庆'})
    if r.get('status') == '1' and r.get('geocodes'):
        return r['geocodes'][0]['location'], r['geocodes'][0]['formatted_address']
    return None, None


def distance_m(destination, mode=3):
    r = get(f'direction/{MODE_PATH[mode]}', {'origin': ORIGIN, 'destination': destination})
    if r.get('status') == '1' and r.get('route', {}).get('paths'):
        p = r['route']['paths'][0]
        return int(p['distance']), int(p['duration'])
    return None, None


SAMPLES = [
    '重庆市大渡口区九宫庙',
    '重庆市大渡口区茄子溪',
    '重庆市渝中区解放碑',
]

for addr in SAMPLES:
    loc, formatted = geocode(addr)
    if not loc:
        print(f'{addr:<20} 地理编码失败')
        continue
    drive, dur = distance_m(loc, 3)
    ride, _ = distance_m(loc, 2)
    ok = '在范围内' if (drive is not None and drive <= RADIUS) else '超出范围'
    print(f'{addr:<20} -> {formatted}')
    print(f'{"":20}    驾车 {drive} 米 / 骑行 {ride} 米  => {ok}')