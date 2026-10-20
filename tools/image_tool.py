"""Real dish-image generation through DashScope, with bounded background jobs."""
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import requests

from . import config

logger = logging.getLogger(__name__)
IMAGE_DIR = config.PROJECT_ROOT / 'ui' / 'public' / 'images' / 'generated'
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='dish-image')
_slots = threading.BoundedSemaphore(8)
_lock = threading.Lock()
_jobs = {}


class ImageGenerationError(RuntimeError):
    pass


def build_prompt(dish):
    name = dish['dish_name'].strip()
    ingredients = dish.get('main_ingredients', '').strip()
    return (
        f'一张让人有食欲的中餐菜品美食摄影，菜名「{name}」，分类「{dish.get("category", "中餐")}」。'
        f'主要食材：{ingredients or "根据菜名采用传统常见食材"}。'
        f'做法与描述：{dish.get("cooking_method", "")}；{dish.get("description", "")}。'
        f'{"严格素食，不出现肉类。" if dish.get("is_vegetarian") else ""}'
        '只展示这一道菜，一份丰盛菜肴放在质感陶瓷餐盘中，完整餐盘居中，占画面80%，'
        '深色胡桃木餐桌，45度俯拍，温暖自然侧光，细腻真实的食物纹理，适度蒸汽，色泽诱人自然，'
        '商业美食摄影，高清晰度。不要人物、文字、商标、水印、菜单或界面，不要额外添加其他菜肴。'
    )[:790]


def _json_request(method, path, **kwargs):
    try:
        response = requests.request(
            method, config.IMAGE_API_BASE.rstrip('/') + path,
            headers={'Authorization': f'Bearer {config.IMAGE_API_KEY}', 'Content-Type': 'application/json',
                     **kwargs.pop('headers', {})}, timeout=(10, 45), **kwargs)
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ImageGenerationError('图片生成服务连接失败，请稍后重试') from exc
    if not response.ok or payload.get('code'):
        code = str(payload.get('code', 'service_error'))[:80]
        if response.status_code in (401, 403):
            raise ImageGenerationError('生图服务凭据或模型权限不可用，请检查服务端百炼配置')
        if response.status_code == 429:
            raise ImageGenerationError('生图服务繁忙，请稍后重试')
        raise ImageGenerationError(f'图片生成服务未完成请求（{code}）')
    return payload


def _download(image_url, job_id):
    parsed = urlsplit(image_url)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.aliyuncs.com'):
        raise ImageGenerationError('生图服务返回的图片地址无效')
    try:
        response = requests.get(image_url, stream=True, timeout=(10, 45), allow_redirects=False)
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 15 * 1024 * 1024:
                raise ImageGenerationError('生成图片过大，请重试')
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            extension = 'png'
        elif data.startswith(b'\xff\xd8\xff'):
            extension = 'jpg'
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            extension = 'webp'
        else:
            raise ImageGenerationError('生图服务未返回有效图片')
    except requests.RequestException as exc:
        raise ImageGenerationError('图片已生成但下载失败，请重新生成') from exc
    finally:
        if 'response' in locals():
            response.close()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{job_id}.{extension}'
    destination = IMAGE_DIR / filename
    pending = destination.with_suffix('.partial')
    pending.write_bytes(data)
    pending.replace(destination)
    return f'/images/generated/{filename}'


def _update(job_id, **values):
    with _lock:
        _jobs[job_id].update(values, updated_at=time.time())


def _run(job_id, dish):
    try:
        _update(job_id, status='running', message='正在构思菜品画面并生成图片…')
        payload = _json_request('POST', '/services/aigc/image-generation/generation',
            headers={'X-DashScope-Async': 'enable'}, json={
                'model': config.IMAGE_MODEL,
                'input': {'messages': [{'role': 'user', 'content': [{'text': build_prompt(dish)}]}]},
                'parameters': {'size': '1328*1328', 'n': 1, 'prompt_extend': True, 'watermark': False}})
        task_id = payload.get('output', {}).get('task_id')
        if not task_id:
            raise ImageGenerationError('生图服务未返回任务编号')
        deadline = time.monotonic() + config.IMAGE_TIMEOUT
        while time.monotonic() < deadline:
            result = _json_request('GET', f'/tasks/{task_id}')
            output = result.get('output', {})
            status = output.get('task_status')
            if status == 'SUCCEEDED':
                images = output.get('results') or []
                choices = output.get('choices') or []
                content = choices[0].get('message', {}).get('content', []) if choices else []
                image_url = images[0].get('url') if images else next((block.get('image') for block in content if block.get('image')), None)
                if not image_url:
                    raise ImageGenerationError('生图任务完成但没有图片结果')
                _update(job_id, message='图片已生成，正在保存…')
                image_url = _download(image_url, job_id)
                _update(job_id, status='succeeded', image_url=image_url, message='图片已生成并保存', source='ai')
                return
            if status in ('FAILED', 'CANCELED', 'UNKNOWN'):
                code = str(output.get('code', status))[:80]
                raise ImageGenerationError(f'图片生成失败（{code}），可调整菜名或描述后重试')
            time.sleep(2)
        raise ImageGenerationError('图片生成超时，请稍后重试')
    except ImageGenerationError as exc:
        _update(job_id, status='failed', message=str(exc))
    except Exception:
        logger.exception('Dish image job failed: %s', job_id)
        _update(job_id, status='failed', message='图片生成未完成，请稍后重试')
    finally:
        _slots.release()


def create_job(dish):
    if not config.IMAGE_API_KEY:
        raise ImageGenerationError('尚未配置图片生成服务，请检查服务端 IMAGE_API_KEY')
    if not _slots.acquire(blocking=False):
        raise ImageGenerationError('已有较多图片正在生成，请稍后重试')
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        expired = [key for key, job in _jobs.items() if job['status'] in ('succeeded', 'failed') and now - job['updated_at'] > 1800]
        for key in expired:
            del _jobs[key]
        _jobs[job_id] = {'job_id': job_id, 'status': 'queued', 'message': '等待生成…', 'updated_at': now}
    try:
        _executor.submit(_run, job_id, dict(dish))
    except Exception:
        _slots.release()
        with _lock:
            del _jobs[job_id]
        raise
    return get_job(job_id)


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise ValueError('图片任务不存在或已失效，请重新生成')
        return {key: value for key, value in job.items() if key != 'updated_at'}
