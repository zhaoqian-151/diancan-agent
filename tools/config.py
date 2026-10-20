"""
配置模块

集中读取项目根目录下的 .env，供 tools 下各模块引用。
所有配置项都在这里转换成正确的类型，其它模块不要直接读 os.environ。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# tools/config.py -> tools/ -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

load_dotenv(ENV_PATH)


def _str(name: str, default: str = '') -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().strip('"').strip("'")


def _int(name: str, default: int) -> int:
    raw = _str(name)
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = _str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------- 大模型
LLM_BASE_URL = _str('LLM_BASE_URL')
LLM_API_KEY = _str('LLM_API_KEY')
LLM_MODEL = _str('LLM_MODEL', 'deepseek-v4.1-flash')
LLM_TEMPERATURE = _float('LLM_TEMPERATURE', 0.7)
LLM_TIMEOUT = _int('LLM_TIMEOUT', 60)
# deepseek-v4.1-flash 是推理模型，推理 token 也计入 completion_tokens，
# 这个值给小了会导致 content 为空，只返回 reasoning_content。
LLM_MAX_TOKENS = _int('LLM_MAX_TOKENS', 4096)

# 菜品配图使用百炼异步生图接口；密钥仅存在服务端。
IMAGE_API_BASE = _str('IMAGE_API_BASE', 'https://dashscope.aliyuncs.com/api/v1')
IMAGE_API_KEY = _str('IMAGE_API_KEY') or (LLM_API_KEY if 'aliyuncs.com' in LLM_BASE_URL else '')
IMAGE_MODEL = _str('IMAGE_MODEL', 'qwen-image-3.0')
IMAGE_TIMEOUT = _int('IMAGE_TIMEOUT', 180)

# ---------------------------------------------------------------- 向量化
EMBEDDING_MODEL = _str('EMBEDDING_MODEL', 'text-embedding-v3')
EMBEDDING_DIMENSION = _int('EMBEDDING_DIMENSION', 1024)

# ---------------------------------------------------------------- Pinecone
PINECONE_API_KEY = _str('PINECONE_API_KEY')
PINECONE_INDEX_NAME = _str('PINECONE_INDEX_NAME', 'menu-item-index')
PINECONE_ENV = _str('PINECONE_ENV', 'us-east-1')
PINECONE_CLOUD = _str('PINECONE_CLOUD', 'aws')

# ---------------------------------------------------------------- MySQL
MYSQL_HOST = _str('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = _int('MYSQL_PORT', 3306)
MYSQL_USER_NAME = _str('MYSQL_USER_NAME', 'root')
MYSQL_USER_PASSWORD = _str('MYSQL_USER_PASSWORD', '')
MYSQL_DB_NAME = _str('MYSQL_DB_NAME', 'menu')
MYSQL_CHARSET = _str('MYSQL_CHARSET', 'utf8mb4')

# ---------------------------------------------------------------- 高德地图
AMAP_API_KEY = _str('AMAP_API_KEY')
AMAP_BASE_URL = _str('AMAP_BASE_URL', 'https://restapi.amap.com/v3')
# 地址不写城市时用的默认城市，能显著提高地理编码命中率
AMAP_DEFAULT_CITY = _str('AMAP_DEFAULT_CITY', '重庆')

# 商户（配送起点）
MERCHANT_NAME = _str('MERCHANT_NAME', '本店')
MERCHANT_ADDRESS = _str('MERCHANT_ADDRESS', '')
MERCHANT_PHONE = _str('MERCHANT_PHONE', '')
MERCHANT_BUSINESS_HOURS = _str('MERCHANT_BUSINESS_HOURS', '')
MERCHANT_LONGITUDE = _float('MERCHANT_LONGITUDE', 0.0)
MERCHANT_LATITUDE = _float('MERCHANT_LATITUDE', 0.0)
DELIVERY_RADIUS = _int('DELIVERY_RADIUS', 2500)
DEFAULT_PATH_MODE = _int('DEFAULT_PATH_MODE', 2)

# 路径规划模式：1-步行，2-骑行（电动车），3-驾车
PATH_MODE_TO_AMAP = {1: 'walking', 2: 'riding', 3: 'driving'}
PATH_MODE_TEXT = {1: '步行', 2: '骑行', 3: '驾车'}

# ---------------------------------------------------------------- 服务
SERVER_HOST = _str('SERVER_HOST', '0.0.0.0')
SERVER_PORT = _int('SERVER_PORT', 8000)

# 商户经纬度字符串，高德接口要 "经度,纬度" 的顺序
MERCHANT_LOCATION = f'{MERCHANT_LONGITUDE},{MERCHANT_LATITUDE}'


def describe() -> str:
    """返回一份脱敏后的配置摘要，用于启动时打印和排查问题。"""
    def mask(value: str) -> str:
        if not value:
            return '(未配置)'
        if len(value) <= 12:
            return value[:4] + '***'
        return f'{value[:8]}...{value[-4:]}'

    return '\n'.join([
        f'  配置文件      : {ENV_PATH}',
        f'  大模型        : {LLM_MODEL} @ {LLM_BASE_URL}',
        f'  大模型密钥    : {mask(LLM_API_KEY)}',
        f'  向量化模型    : {EMBEDDING_MODEL} ({EMBEDDING_DIMENSION} 维)',
        f'  Pinecone 索引 : {PINECONE_INDEX_NAME} (密钥 {mask(PINECONE_API_KEY)})',
        f'  MySQL         : {MYSQL_USER_NAME}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB_NAME}',
        f'  高德密钥      : {mask(AMAP_API_KEY)}',
        f'  商户          : {MERCHANT_NAME} ({MERCHANT_LOCATION})',
        f'  配送范围      : {DELIVERY_RADIUS} 米，默认{PATH_MODE_TEXT.get(DEFAULT_PATH_MODE, "?")}',
        f'  服务端口      : {SERVER_PORT}',
    ])
