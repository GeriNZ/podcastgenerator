import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).with_name('app.py'))

class AccessTests(unittest.TestCase):
    def app(self):
        at = AppTest.from_file(APP)
        at.secrets['APP_PASSWORD'] = 'test-access-only'
        at.secrets['ENABLE_GENERATION'] = 'false'
        at.run()
        self.assertFalse(at.exception)
        return at

    def test_login_gate_and_generation_lock(self):
        with patch('modal.Function.from_name', side_effect=AssertionError('GPU lookup must not happen')):
            at = self.app()
            self.assertEqual(len(at.text_area), 0)
            at.text_input[0].set_value('wrong')
            at.button[0].click().run()
            self.assertEqual(len(at.text_area), 0)
            at.session_state['retry_after'] = 0
            at.text_input[0].set_value('test-access-only')
            at.button[0].click().run()
            self.assertFalse(at.exception)
            generate = next(b for b in at.button if b.label == 'Generate preview')
            self.assertTrue(generate.disabled)
            at.text_area[0].set_value('Missing speaker label').run()
            self.assertTrue(at.warning)
            next(b for b in at.button if b.label == 'Sign out').click().run()
            self.assertEqual(len(at.text_area), 0)

    def test_missing_password_fails_closed(self):
        at = AppTest.from_file(APP)
        at.secrets['APP_PASSWORD'] = ''
        at.run()
        self.assertTrue(at.error)
        self.assertEqual(len(at.text_area), 0)

if __name__ == '__main__':
    unittest.main()
