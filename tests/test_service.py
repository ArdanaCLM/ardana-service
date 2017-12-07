import testtools
import mock
import json
import os
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from flask import Flask
from ardana_service.service import bp

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
        y = json.loads(x.data)
        self.assertEquals(len(y), 1)
        self.assertEquals(y[0]['files'][0], 'test.j2')

    @mock.patch('os.walk')
    def test_get_all_files_subdir(self, mock_os_walk):

        self.conf.config(group='paths', config_dir='/root')
        mock_os_walk.return_value = \
            [('/root', ['dir1'], []), ('/root/dir1', ['subdir'], []),
                ('/root/dir1/subdir', [], ['test.j2'])]
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files')
        y = json.loads(x.data)
        self.assertEquals(len(y), 1)
        self.assertEquals(y[0]['files'][0], 'subdir/test.j2')

    @mock.patch('os.walk')
    def test_get_all_files_emptydir(self, mock_os_walk):

        self.conf.config(group='paths', config_dir='/root')
        mock_os_walk.return_value = \
            [('/root', ['dir1'], []), ('/root/dir1', [], [])]
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files')
        y = json.loads(x.data)
        self.assertEquals(len(y), 0)

    def test_get_a_file(self):

        self.conf.config(group='paths',
                         config_dir=self.TEST_DATA_DIR + '/service_files/')
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files/testservice/test.j2')
        y = json.loads(x.data)
        content = 'log_config_append={{ cinder_api_conf_dir }}' + \
                  '/api-logging.conf'
        self.assertTrue(y.find(content))

    def test_post_a_file(self):

        self.conf.config(group='paths',
                         config_dir=self.TEST_DATA_DIR + '/service_files/')
        myapp = app.test_client()
        x = myapp.get('/api/v2/service/files/testservice/test.j2')
        y = json.loads(x.data)
        result = myapp.post(
            '/api/v2/service/files/testservice/test.j2',
            data=json.dumps(y),
            content_type='application/json')
        self.assertTrue(str(result).find('200'))
