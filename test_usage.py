import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from streamlit.testing.v1 import AppTest
from usage import estimate, UsageSheet, HEADERS

class UsageTests(unittest.TestCase):
    def test_cost_units_and_credits_not_subtracted(self):
        result = estimate({}, report={'audio_seconds': 7.74, 'total_seconds': 36.245})
        self.assertAlmostEqual(result['cost'], 44.245 * (.80 + .0473 + 4 * .008) / 3600)
        self.assertEqual(estimate({}, words=1000)['audio_seconds'], 30)
        with self.assertRaises(ValueError):
            estimate({'GPU_USD_HOUR': 'nan'})

    def test_redirect_does_not_forward_secret(self):
        with patch('requests.post') as post, patch('requests.get') as get:
            post.return_value.status_code = 302
            post.return_value.headers = {'Location': 'https://script.googleusercontent.com/macros/echo?test=1'}
            get.return_value.json.return_value = {'ok': True, 'request_id': 'abc'}
            ledger = UsageSheet({'USAGE_SCRIPT_URL': 'https://script.google.com/macros/s/test/exec', 'USAGE_SCRIPT_SECRET': 'private'})
            ledger.upsert({'request_id': 'abc', 'title': '=formula', 'script': 'must not be sent'})
            self.assertNotIn('script', post.call_args.kwargs['json']['record'])
            self.assertNotIn('json', get.call_args.kwargs)
            self.assertNotIn('private', get.call_args.args[0])

    def test_rejected_response_is_not_success(self):
        with patch('requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'ok': False}
            ledger = UsageSheet({'USAGE_SCRIPT_URL': 'https://script.google.com/macros/s/test/exec', 'USAGE_SCRIPT_SECRET': 'private'})
            with self.assertRaises(RuntimeError):
                ledger.check()

    def logged_in(self):
        app = AppTest.from_file(str(Path(__file__).with_name('app.py')))
        app.secrets.update(APP_PASSWORD='test', ENABLE_GENERATION='true',
                           USAGE_SCRIPT_URL='https://script.google.com/macros/s/test/exec', USAGE_SCRIPT_SECRET='fake')
        app.run()
        app.text_input[0].set_value('test')
        app.button[0].click().run()
        app.text_input[0].set_value('Test title').run()
        return app

    def test_records_success_without_script_and_no_rerun_duplication(self):
        with patch('settings.modal_client'), patch('usage.UsageSheet') as factory, patch('modal.Function.from_name') as remote:
            remote.return_value.remote.return_value = {'audio': b'RIFFtest', 'report': {'audio_seconds': 5, 'total_seconds': 20}}
            app = self.logged_in()
            next(b for b in app.button if b.label == 'Generate preview').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(factory.return_value.upsert.call_count, 2)
            record = factory.return_value.upsert.call_args.args[0]
            self.assertEqual(record['status'], 'completed')
            self.assertNotIn('script', record)
            self.assertIn('estimated_cost_usd', record)
            app.run()
            self.assertEqual(remote.return_value.remote.call_count, 1)
            self.assertEqual(factory.return_value.upsert.call_count, 2)

    def test_logging_failure_blocks_gpu(self):
        with patch('settings.modal_client'), patch('usage.UsageSheet') as factory, patch('modal.Function.from_name') as remote:
            factory.return_value.upsert.side_effect = RuntimeError('offline')
            app = self.logged_in()
            next(b for b in app.button if b.label == 'Generate preview').click().run()
            self.assertFalse(app.exception)
            remote.assert_not_called()
            self.assertEqual(app.session_state['pending_usage']['status'], 'not_submitted_logging_error')

    def test_final_log_retry_does_not_repeat_generation(self):
        with patch('settings.modal_client'), patch('usage.UsageSheet') as factory, patch('modal.Function.from_name') as remote:
            remote.return_value.remote.return_value = {'audio': b'RIFFtest', 'report': {'audio_seconds': 5, 'total_seconds': 20}}
            factory.return_value.upsert.side_effect = [None, RuntimeError('offline'), None]
            app = self.logged_in()
            next(b for b in app.button if b.label == 'Generate preview').click().run()
            app.run()
            next(b for b in app.button if b.label == 'Retry saving usage record').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(remote.return_value.remote.call_count, 1)
            self.assertNotIn('pending_usage', app.session_state)

if __name__ == '__main__':
    unittest.main()
