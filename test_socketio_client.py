import json
import logging
import requests

from socketIO_client import LoggingNamespace
from socketIO_client import SocketIO

logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
logging.basicConfig()


def on_message(message):
    # message is a json-formatted string of args prefixed with '2'
    # (which means it is an event), plus any namespace.  So, if
    # the message is in the /log namespace, it will be in the format
    # 2/log["the message"]
    args = json.loads(message.lstrip('2'))
    print(args[1],)


socketIO = SocketIO('localhost', 9085, LoggingNamespace)
socketIO.on('message', on_message)

r = requests.post("http://localhost:9085/api/v2/playbooks/venv-edit")
id = r.headers['Location'].split('/')[-1]

socketIO.emit('join', id)

socketIO.wait(seconds=4)
