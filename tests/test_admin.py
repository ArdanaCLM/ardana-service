# (c) Copyright 2017-2018 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import Flask
from oslo_serialization import jsonutils
import testtools

from ardana_service.admin import bp

app = Flask(__name__)
app.register_blueprint(bp)


class TestAdmin(testtools.TestCase):

    def test_get_user(self):
        # Execute without mocking to verify that the real operating system
        #    calls are being executed without error
        test_app = app.test_client()
        resp = test_app.get('/api/v2/user')
        user_dict = jsonutils.loads(resp.data)

        # Since we cannot control which username that this unit test runs
        # under, we only require that it return a non-empty username
        self.assertIn('username', user_dict)
        username = user_dict['username']
        self.assertNotEqual('', username)
