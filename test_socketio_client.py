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

from __future__ import print_function
import argparse
import logging
import requests
from socketIO_client import BaseNamespace
from socketIO_client import SocketIO

parser = argparse.ArgumentParser()
parser.add_argument('-u', '--username', default='admin')
parser.add_argument('-p', '--password')
parser.add_argument('-H', '--host', default='localhost')
parser.add_argument('-P', '--port', type=int, default=9085)
parser.add_argument('-s', '--scheme', default='http',
                    choices=['http', 'https'])
parser.add_argument('-v', '--verify', action='store_true')
parser.add_argument('playbook')
args = parser.parse_args()

if args.port == 9085:
    base_url = "%s://%s:%d/api/v2" % (args.scheme, args.host, args.port)
else:
    base_url = "%s://%s:%d/api/v1/clm" % (args.scheme, args.host, args.port)

# Uncomment the next line to enable debugging messages
logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
logging.basicConfig()


def on_log(message):
    print(message, end='')


def on_end(message):
    # Disconnect the socket.  This will also interrupt the wait(),
    # causing the program to end
    print("End received, disconnecting...")
    socketIO.disconnect()


def on_playbook_start(playbook):
    print("Playbook %s started" % (args.playbook))


def on_playbook_end(playbook):
    print("Playbook %s ended" % (args.playbook))


def on_playbook_error(playbook):
    print("Playbook %s error" % (args.playbook))


resp = requests.get(base_url + "/is_secured", verify=args.verify)
resp.raise_for_status()

headers = None

# Login and obtain an auth token if necessary
if resp.json()['isSecured']:

    print("Getting auth token")
    payload = {
        'username': args.username,
        'password': args.password,
    }

    resp = requests.post(base_url + "/login", json=payload,
                         verify=args.verify)
    resp.raise_for_status()

    headers = {'X-Auth-Token': resp.json()['token']}

if args.scheme == 'http':
    host = args.host
else:
    host = '%s://%s' % (args.scheme, args.host)

socketIO = SocketIO(host, args.port, BaseNamespace, verify=args.verify)
socketIO.on('log', on_log)
socketIO.on('end', on_end)
socketIO.on('playbook-start', on_playbook_start)
socketIO.on('playbook-error', on_playbook_error)

print("Launching playbook")
resp = requests.post(base_url + "/playbooks/" + args.playbook,
                     verify=args.verify, headers=headers)
resp.raise_for_status()

# Extract the play id from the response
id = resp.headers['Location'].split('/')[-1]

# Join the room where the log messages will be broadcast
socketIO.emit('join', id)

# Wait indefinitely
socketIO.wait()
