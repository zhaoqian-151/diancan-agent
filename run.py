"""
智能点餐助手 启动脚本

启动uvicorn web服务器
"""

import argparse
import logging
import sys
from pathlib import Path

# 允许直接 python run.py 运行（把项目根目录加进模块搜索路径）
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn  # noqa: E402

from agent import assistant  # noqa: E402
from api.main import app  # noqa: E402
from tools import config  # noqa: E402

# Windows 控制台默认是 GBK，中文日志会乱码
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def print_banner(host: str, port: int) -> None:
    shown_host = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    print('=' * 66)
    print('  智能点餐助手 后端服务')
    print('=' * 66)
    print('配置：')
    print(config.describe())
    print('组件：')
    print(assistant.describe())
    print('地址：')
    print(f'  接口文档  http://{shown_host}:{port}/docs')
    print(f'  健康检查  http://{shown_host}:{port}/health')
    print(f'  菜品列表  http://{shown_host}:{port}/menu/list')
    print('=' * 66)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description='启动智能点餐助手后端服务')
    parser.add_argument('--host', default=config.SERVER_HOST,
                        help=f'监听地址，默认 {config.SERVER_HOST}')
    parser.add_argument('--port', type=int, default=config.SERVER_PORT,
                        help=f'监听端口，默认 {config.SERVER_PORT}')
    parser.add_argument('--reload', action='store_true',
                        help='代码改动后自动重启（开发用）')
    parser.add_argument('--log-level', default='info',
                        choices=['critical', 'error', 'warning', 'info', 'debug'],
                        help='日志级别，默认 info')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    # 第三方库的 INFO 日志太吵，只保留警告以上
    for noisy in ('httpx', 'httpx2', 'httpcore', 'openai', 'urllib3', 'asyncio'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print_banner(args.host, args.port)

    # reload 模式必须传 import 字符串，uvicorn 要另起进程重新导入
    target = 'api.main:app' if args.reload else app
    uvicorn.run(
        target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == '__main__':
    main()