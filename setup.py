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
#
from setuptools import find_packages
from setuptools import setup

setup(
    name='ardana-service',
    version='1.0.0',
    author='SUSE LLC',
    author_email='ardana@googlegroups.com',
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    scripts=[],
    url='https://github.com/ArdanaCLM',
    license='Apache-2.0',
    description='OpenStack Ardana Lifecycle Management Server',
    long_description=open('README.rst').read(),
    install_requires=['Flask', 'eventlet', 'flask-socketio', 'flask-cors',
                      'gitpython', 'oslo.config', 'oslo.log',
                      'keystonemiddleware'],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'ardana-service = ardana_service.main:main',
        ],
        'oslo.config.opts': [
            'ardana_service = ardana_service.config:list_opts',
        ],
    }
)
