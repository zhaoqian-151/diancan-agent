"""
高德地图工具模块

该模块提供高德地图的API调用功能，
用于获取地图上的地点信息、路线规划等

对外主要提供四个能力：
- geocode         地址 -> 经纬度
- regeocode       经纬度 -> 地址
- get_route       两点之间的路径距离与耗时
- check_delivery_range  判断某个地址是否在配送范围内（前端配送查询接口的数据来源）
"""

import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

from . import config

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class AmapError(RuntimeError):
    """高德接口调用失败。"""


# ---------------------------------------------------------------- 底层请求

def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """调用高德 Web 服务接口，统一处理错误码。"""
    if not config.AMAP_API_KEY:
        raise AmapError(f'未配置 AMAP_API_KEY，请检查 {config.ENV_PATH}')

    query = dict(params)
    query['key'] = config.AMAP_API_KEY
    query.setdefault('output', 'JSON')
    url = f'{config.AMAP_BASE_URL}/{path}?{urlencode(query)}'

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise AmapError(f'请求高德接口失败（{path}）：{exc}') from exc
    except ValueError as exc:
        raise AmapError(f'高德接口返回的不是合法 JSON（{path}）') from exc

    # 高德用 status=1 表示成功，info 里是原因
    if str(data.get('status')) != '1':
        raise AmapError(f"高德接口报错（{path}）：{data.get('info')} "
                        f"[infocode={data.get('infocode')}]")
    return data


# ---------------------------------------------------------------- 地理编码

def geocode(address: str, city: Optional[str] = None) -> Dict[str, Any]:
    """把地址转成经纬度。

    返回 {'success', 'longitude', 'latitude', 'location', 'formatted_address',
          'district', 'city', 'level'}；找不到时 success 为 False。
    """
    if not address or not address.strip():
        return {'success': False, 'message': '地址不能为空'}

    params = {'address': address.strip()}
    city = city or config.AMAP_DEFAULT_CITY
    if city:
        params['city'] = city

    data = _request('geocode/geo', params)
    geocodes = data.get('geocodes') or []
    if not geocodes:
        return {'success': False,
                'message': f'无法识别地址「{address}」，请补充城市或更详细的描述'}

    best = geocodes[0]
    lng, lat = (best.get('location') or ',').split(',')
    return {
        'success': True,
        'longitude': float(lng),
        'latitude': float(lat),
        'location': best.get('location'),
        'formatted_address': best.get('formatted_address') or address,
        'district': best.get('district') or '',
        'city': best.get('city') or '',
        'level': best.get('level') or '',
        'candidates': [g.get('formatted_address') for g in geocodes[1:4]],
    }


def regeocode(longitude: float, latitude: float) -> Dict[str, Any]:
    """把经纬度转回文字地址。"""
    data = _request('geocode/regeo', {'location': f'{longitude},{latitude}'})
    regeo = data.get('regeocode') or {}
    component = regeo.get('addressComponent') or {}
    return {
        'success': bool(regeo.get('formatted_address')),
        'formatted_address': regeo.get('formatted_address') or '',
        'province': component.get('province') or '',
        'city': component.get('city') or '',
        'district': component.get('district') or '',
        'township': component.get('township') or '',
    }


# ---------------------------------------------------------------- 路径规划

def get_route(
    destination: str,
    origin: Optional[str] = None,
    mode: Optional[int] = None,
) -> Dict[str, Any]:
    """计算从商户到目的地（或任意两点）的路径距离与耗时。

    destination / origin 既可以是「经度,纬度」，也可以是文字地址。
    mode：1-步行，2-骑行，3-驾车。
    """
    mode = int(mode or config.DEFAULT_PATH_MODE)
    if mode not in config.PATH_MODE_TO_AMAP:
        raise ValueError(f'不支持的出行方式：{mode}（应为 1/2/3）')

    origin_loc = _resolve_location(origin) if origin else {
        'success': True,
        'location': config.MERCHANT_LOCATION,
        'formatted_address': config.MERCHANT_NAME,
    }
    dest = _resolve_location(destination)

    if not origin_loc['success']:
        return {'success': False, 'message': f"起点无法定位：{origin_loc.get('message')}"}
    if not dest['success']:
        return {'success': False, 'message': dest.get('message'),
                'formatted_address': destination}

    data = _request(f"direction/{config.PATH_MODE_TO_AMAP[mode]}",
                    {'origin': origin_loc['location'], 'destination': dest['location']})

    paths = (data.get('route') or {}).get('paths') or []
    if not paths:
        return {'success': False,
                'message': f"未能规划出从本店到「{dest['formatted_address']}」的"
                           f"{config.PATH_MODE_TEXT[mode]}路线",
                'formatted_address': dest['formatted_address']}

    best = paths[0]
    return {
        'success': True,
        'distance_m': int(float(best.get('distance', 0))),
        'duration_s': int(float(best.get('duration', 0))),
        'travel_mode': mode,
        'travel_mode_text': config.PATH_MODE_TEXT[mode],
        'formatted_address': dest['formatted_address'],
        'destination_level': dest.get('level') or '',
        'origin_location': origin_loc['location'],
        'destination_location': dest['location'],
    }


def _resolve_location(value: str) -> Dict[str, Any]:
    """判断入参是「经度,纬度」还是文字地址，统一转成经纬度。"""
    text = (value or '').strip()
    parts = text.split(',')
    if len(parts) == 2:
        try:
            float(parts[0])
            float(parts[1])
            return {'success': True, 'location': text,
                    'formatted_address': text, 'level': '经纬度'}
        except ValueError:
            pass

    result = geocode(text)
    if not result['success']:
        return result
    return {'success': True, 'location': result['location'],
            'formatted_address': result['formatted_address'],
            'level': result.get('level') or ''}


# ---------------------------------------------------------------- 配送范围

def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    if minutes <= 0:
        return f'{secs} 秒'
    if secs == 0:
        return f'{minutes} 分钟'
    return f'{minutes} 分 {secs} 秒'


def get_merchant_info() -> Dict[str, Any]:
    """本店信息，供「餐厅信息查询」使用。"""
    address = ''
    try:
        address = regeocode(config.MERCHANT_LONGITUDE, config.MERCHANT_LATITUDE)['formatted_address']
    except AmapError as exc:
        logger.warning('逆地理编码获取本店地址失败：%s', exc)

    return {
        'name': config.MERCHANT_NAME,
        'address': address,
        'phone': config.MERCHANT_PHONE,
        'business_hours': config.MERCHANT_BUSINESS_HOURS,
        'longitude': config.MERCHANT_LONGITUDE,
        'latitude': config.MERCHANT_LATITUDE,
        'location': config.MERCHANT_LOCATION,
        'delivery_radius': config.DELIVERY_RADIUS,
        'delivery_radius_text': f'{config.DELIVERY_RADIUS / 1000:.1f} 公里',
        'default_path_mode': config.DEFAULT_PATH_MODE,
        'default_path_mode_text': config.PATH_MODE_TEXT.get(config.DEFAULT_PATH_MODE, ''),
    }


def _looks_mismatched(query: str, formatted: str) -> bool:
    """判断高德返回的地址和用户输入是否毫无关系。

    高德遇到识别不了的输入会模糊匹配到某个毫不相干的地方（例："不存在的地址乱码xyz"
    被匹配到内蒙古一个乡镇）。这里用「有没有长度>=2 的公共片段」来判断：
    完全对不上就认为是低置信度，让上层提示用户补充地址。
    """
    import re
    q = re.sub(r'[\s,，。.、;；:：]+', '', query or '')
    f = re.sub(r'[\s,，。.、;；:：]+', '', formatted or '')
    if not q or not f:
        return True
    if len(q) < 2:
        return q not in f
    for size in range(len(q), 1, -1):
        for start in range(len(q) - size + 1):
            if q[start:start + size] in f:
                return False
    return True


def check_delivery_range(address: str, travel_mode: Optional[int] = None) -> Dict[str, Any]:
    """判断地址是否在外卖配送范围内。

    返回结构直接给前端「配送查询」区域使用：
    distance 单位是公里，duration 单位是秒。
    """
    mode = int(travel_mode or config.DEFAULT_PATH_MODE)
    if mode not in config.PATH_MODE_TO_AMAP:
        mode = config.DEFAULT_PATH_MODE
    mode_text = config.PATH_MODE_TEXT[mode]
    radius_km = config.DELIVERY_RADIUS / 1000

    base = {
        'success': False, 'in_range': False, 'distance': 0, 'duration': 0,
        'formatted_address': '', 'message': '', 'travel_mode': mode,
        'travel_mode_text': mode_text, 'radius': config.DELIVERY_RADIUS,
        'radius_km': radius_km, 'merchant': config.MERCHANT_NAME,
    }

    if not address or not address.strip():
        base['message'] = '请输入要查询的收货地址。'
        return base

    try:
        route = get_route(address, mode=mode)
    except AmapError as exc:
        base['message'] = f'地址解析失败：{exc}'
        return base

    if not route['success']:
        base['message'] = route.get('message', '地址解析失败，请更换更详细的地址后重试。')
        base['formatted_address'] = route.get('formatted_address', '')
        return base

    distance_km = round(route['distance_m'] / 1000, 2)
    duration_s = route['duration_s']
    in_range = route['distance_m'] <= config.DELIVERY_RADIUS
    level = route.get('destination_level') or ''

    base.update({
        'success': True,
        'in_range': in_range,
        'distance': distance_km,
        'duration': duration_s,
        'duration_text': _format_duration(duration_s),
        'formatted_address': route['formatted_address'],
        'address_level': level,
        # 高德遇到识别不了的地址会模糊匹配到某个省份/城市，
        # 这种粗略结果要提示用户补充信息，不能当成准确地址。
        'low_confidence': _looks_mismatched(address, route['formatted_address']),
        'longitude': float(route['destination_location'].split(',')[0]),
        'latitude': float(route['destination_location'].split(',')[1]),
    })

    if base['low_confidence']:
        # 地址都没认出来，距离数字是模糊匹配到的无关地点算出来的，
        # 留着会让前端把它显示成真实配送距离（例如"1959 公里"），
        # 所以清零，只让用户看到"请补充地址"的提示。
        base['distance'] = 0
        base['duration'] = 0
        base['duration_text'] = ''
        base['message'] = (
            f'没能识别地址「{address}」。高德把它模糊匹配到了'
            f'「{route["formatted_address"]}」（{level or "层级未知"}），'
            f'与您输入的内容对不上。请补充所在城市或更具体的地点（如医院、学校、小区名）后再查。'
        )
        return base

    if in_range:
        base['message'] = (
            f'可以配送！到「{route["formatted_address"]}」{mode_text}约 '
            f'{distance_km:.2f} 公里、{_format_duration(duration_s)}，'
            f'在 {radius_km:.1f} 公里配送范围内。'
        )
    else:
        over = round(distance_km - radius_km, 2)
        base['message'] = (
            f'抱歉，该地址超出配送范围。到「{route["formatted_address"]}」{mode_text}约 '
            f'{distance_km:.2f} 公里、{_format_duration(duration_s)}，'
            f'超出 {radius_km:.1f} 公里范围 {over:.2f} 公里。'
        )
    return base


def check_connection() -> Dict[str, Any]:
    """高德接口连通性自检。"""
    merchant = get_merchant_info()
    return {
        'merchant_name': merchant['name'],
        'merchant_address': merchant['address'],
        'location': merchant['location'],
        'delivery_radius': merchant['delivery_radius'],
    }