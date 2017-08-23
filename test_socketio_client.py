import json
import logging
import requests
from socketIO_client import LoggingNamespace
from socketIO_client import SocketIO
import sys

HOST = "localhost"
PORT = 9085
BASE_URL = "http://%s:%d/api/v2" % (HOST, PORT)

# Uncomment the next line to enable debugging messages
# logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
logging.basicConfig()


def on_message(message):
    # message is a json-formatted string of args prefixed with '2'
    # (which means it is an event), plus any namespace.  So, if
    # the message is in the /log namespace, it will be in the format
    # 2/log["the message"]
    args = json.loads(message.lstrip('2'))
    if args[0] == "end":
        # Disconnect the socket.  This will also interrupt the wait(),
        # causing the program to end
        socketIO.disconnect()
    else:
        print args[1],


r = requests.get(BASE_URL + "/playbooks")
playbooks = r.json()
if not playbooks:
    print "No playbooks found"
    sys.exit(0)

socketIO = SocketIO(HOST, PORT, LoggingNamespace)
socketIO.on('message', on_message)

# Start the first playbook found in the list
r = requests.post(BASE_URL + "/playbooks/" + playbooks[0])

# Extract the play id from the response
id = r.headers['Location'].split('/')[-1]

# Join the room where the log messages will be broadcast
socketIO.emit('join', id)

# Wait indefinitely
socketIO.wait()
