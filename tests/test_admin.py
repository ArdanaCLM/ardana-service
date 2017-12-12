import json
import testtools
from flask import Flask
from ardana_service.admin import bp

app = Flask(__name__)
app.register_blueprint(bp)


class TestAdmin(testtools.TestCase):

    def test_get_user(self):
        # Execute without mocking to verify that the real operating system
        #    calls are being executed without error
        test_app = app.test_client()
        resp = test_app.get('/api/v2/user')
        user_dict = json.loads(resp.data)

        # Since we cannot control which username that this unit test runs
        # under, we only require that it return a non-empty username
        self.assertIn('username', user_dict)
        username = user_dict['username']
        self.assertNotEqual('', username)
