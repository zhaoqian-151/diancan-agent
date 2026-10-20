"""Image workflow regressions. Provider calls are mocked; no paid calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.main import app
from tools import image_tool, db_tool


class ImageJobTests(unittest.TestCase):
    def test_prompt_respects_dish_and_vegetarian(self):
        prompt = image_tool.build_prompt({'dish_name': '蒜蓉西兰花', 'main_ingredients': '西兰花,蒜', 'is_vegetarian': True, 'description': 'x' * 1000})
        self.assertIn('蒜蓉西兰花', prompt)
        self.assertLessEqual(len(prompt), 790)
        self.assertIn('严格素食', image_tool.build_prompt({'dish_name': '素菜', 'is_vegetarian': True}))

    def test_reject_untrusted_image_hosts(self):
        for url in ('http://example.com/x.png', 'https://example.com/x.png', 'https://aliyuncs.com.evil.com/x.png', 'http://127.0.0.1/x.png'):
            with self.assertRaises(image_tool.ImageGenerationError):
                image_tool._download(url, 'test')

    def test_transport_errors_do_not_expose_credentials(self):
        import requests
        with patch.object(image_tool.requests, 'request', side_effect=requests.ConnectionError('secret request')):
            with self.assertRaisesRegex(image_tool.ImageGenerationError, '连接失败') as context:
                image_tool._json_request('GET', '/tasks/test')
            self.assertNotIn('secret', str(context.exception))

    def test_missing_image_configuration_is_explicit(self):
        with patch.object(image_tool.config, 'IMAGE_API_KEY', ''):
            response = TestClient(app).post('/admin/menu/image-jobs', json={'dish_name': '清炒时蔬'})
            self.assertEqual(response.status_code, 503)

    def test_missing_job_returns_not_found(self):
        self.assertEqual(TestClient(app).get('/admin/menu/image-jobs/unknown-job').status_code, 404)

    def test_blank_dish_rejected_without_paid_request(self):
        with patch.object(image_tool, 'create_job') as create:
            response = TestClient(app).post('/admin/menu/image-jobs', json={'dish_name': '  '})
            self.assertEqual(response.status_code, 400)
            create.assert_not_called()

    def test_new_protocol_is_parsed_and_stored_locally(self):
        job_id = 'unit-success'
        replies = [{'output': {'task_id': 'provider-task'}}, {'output': {
            'task_status': 'SUCCEEDED', 'choices': [{'message': {'content': [{'image': 'https://result.aliyuncs.com/a.png'}]}}]}}]
        with patch.object(image_tool, '_jobs', {job_id: {'job_id': job_id}}), patch.object(image_tool, '_slots') as slots, patch.object(image_tool, '_json_request', side_effect=replies) as request, patch.object(image_tool, '_download', return_value='/images/generated/test.png'):
            image_tool._run(job_id, {'dish_name': '宫保鸡丁'})
            job = image_tool.get_job(job_id)
            self.assertEqual(job['status'], 'succeeded')
            self.assertEqual(job['image_url'], '/images/generated/test.png')
            self.assertEqual(job['source'], 'ai')
            self.assertIn('messages', request.call_args_list[0].kwargs['json']['input'])
            slots.release.assert_called_once()

    def test_provider_failure_never_returns_an_image(self):
        job_id = 'unit-failed'
        replies = [{'output': {'task_id': 'provider-task'}}, {'output': {'task_status': 'FAILED', 'code': 'TestError'}}]
        with patch.object(image_tool, '_jobs', {job_id: {'job_id': job_id}}), patch.object(image_tool, '_slots') as slots, patch.object(image_tool, '_json_request', side_effect=replies):
            image_tool._run(job_id, {'dish_name': '宫保鸡丁'})
            job = image_tool.get_job(job_id)
            self.assertEqual(job['status'], 'failed')
            self.assertNotIn('image_url', job)
            slots.release.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
