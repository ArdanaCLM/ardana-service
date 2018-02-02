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

import logging
import random
import requests
from socketIO_client import LoggingNamespace
from socketIO_client import SocketIO
import sys

HOST = "localhost"
PORT = 8081  # shim
# PORT = 9085  # ardana-service directly

if PORT == 9085:
    BASE_URL = "http://%s:%d/api/v2" % (HOST, PORT)
else:
    BASE_URL = "http://%s:%d/api/v1/clm" % (HOST, PORT)

# Uncomment the next line to enable debugging messages
logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
logging.basicConfig()


def on_log(message):
    print message,


def on_end(message):
    # Disconnect the socket.  This will also interrupt the wait(),
    # causing the program to end
    socketIO.disconnect()


def on_playbook_start(playbook):
    print "Playbook %s started" % (playbook)


def on_playbook_end(playbook):
    print "Playbook %s ended" % (playbook)


def on_playbook_error(playbook):
    print "Playbook %s error" % (playbook)


r = requests.get(BASE_URL + "/playbooks")
playbooks = r.json()
if not playbooks:
    print "No playbooks found"
    sys.exit(0)

socketIO = SocketIO(HOST, PORT, LoggingNamespace)
socketIO.on('log', on_log)
socketIO.on('end', on_end)
socketIO.on('playbook-start', on_playbook_start)
socketIO.on('playbook-error', on_playbook_error)

# Start some playbook in the list
playbook = random.choice(playbooks)
r = requests.post(BASE_URL + "/playbooks/" + playbook)

# Extract the play id from the response
id = r.headers['Location'].split('/')[-1]

# Join the room where the log messages will be broadcast
socketIO.emit('join', id)

# Wait indefinitely
socketIO.wait()
