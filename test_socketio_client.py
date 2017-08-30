import logging
import random
import requests
from socketIO_client import BaseNamespace
from socketIO_client import LoggingNamespace
from socketIO_client import SocketIO
import sys
import time

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
socketIO.on('playbook-stop', on_playbook_stop)
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
