import unittest
import mock
import json
from flask import Flask
from ardana_service.admin import bp

app = Flask(__name__)
app.register_blueprint(bp)

class TestAdmin(unittest.TestCase):

    @mock.patch('os.getlogin')
    def test_get_user(self, mock_os_getlogin):
        mock_os_getlogin.return_value = "gobbledygook"
        test_app = app.test_client()
        resp = test_app.get('/api/v2/user')
        user_dict = json.loads(resp.data)
        self.assertEquals(user_dict['username'], 'gobbledygook')
