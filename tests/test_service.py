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

import mock
import os
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from oslo_serialization import jsonutils
import testtools

from ardana_service.service import bp
from flask import Flask

app = Flask(__name__)
app.register_blueprint(bp)


class TestServiceFiles(testtools.TestCase):

    def setUp(self):
        super(TestServiceFiles, self).setUp()
        self.TEST_DATA_DIR = os.path.join(os.path.dirname(__file__),
                                          'test_data')
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))

    @mock.patch('os.walk')
    def test_get_all_files(self, mock_os_walk):

        self.conf.config(group='paths', config_dir='/root')
        mock_os_walk.return_value = \
            [('/root', ['dir1'], []), ('/root/dir1', [], ['test.j2'])]
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files')
        y = jsonutils.loads(x.data)
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0]['files'][0], 'test.j2')

    @mock.patch('os.walk')
    def test_get_all_files_subdir(self, mock_os_walk):

        self.conf.config(group='paths', config_dir='/root')
        mock_os_walk.return_value = \
            [('/root', ['dir1'], []), ('/root/dir1', ['subdir'], []),
                ('/root/dir1/subdir', [], ['test.j2'])]
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files')
        y = jsonutils.loads(x.data)
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0]['files'][0], 'subdir/test.j2')

    @mock.patch('os.walk')
    def test_get_all_files_emptydir(self, mock_os_walk):

        self.conf.config(group='paths', config_dir='/root')
        mock_os_walk.return_value = \
            [('/root', ['dir1'], []), ('/root/dir1', [], [])]
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files')
        y = jsonutils.loads(x.data)
        self.assertEqual(len(y), 0)

    def test_get_a_file(self):

        self.conf.config(group='paths',
                         config_dir=self.TEST_DATA_DIR + '/service_files/')
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files/testservice/test.j2')
        y = jsonutils.loads(x.data)
        content = 'log_config_append={{ cinder_api_conf_dir }}' + \
                  '/api-logging.conf'
        self.assertTrue(y.find(content))

    def test_post_a_file(self):

        self.conf.config(group='paths',
                         config_dir=self.TEST_DATA_DIR + '/service_files/')
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files/testservice/test.j2')
        y = jsonutils.loads(x.data)
        result = myapp.post(
            '/api/v2/service/files/testservice/test.j2',
            data=jsonutils.dumps(y),
            content_type='application/json')
        self.assertTrue(str(result).find('200'))
