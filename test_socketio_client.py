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


socketIO = SocketIO('localhost', 5000, LoggingNamespace)

socketIO.on('message', on_message)  # , path='/log')

r = requests.post("http://localhost:5000/api/v2/playbooks/blather")
id = r.headers['Location'].split('/')[-1]

socketIO.emit('join', id)   # , path="/log")

socketIO.wait(seconds=4)
