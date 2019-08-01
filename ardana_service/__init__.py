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

from eventlet import monkey_patch as monkey_patch
# IMPORTANT!
# When using eventlet, monkey_patch is needed in order to properly handle
# IO asynchronously.  Without this, the reading of stdout from the playbook
# run will block until after that playbook has finished.

# The monkey_patch call must be made before importing SocketIO or else
# the requests library may end up in an infinite recursion, as documented
# here: https://github.com/gevent/gevent/issues/941
monkey_patch()

from flask_socketio import SocketIO   # noqa: E402

# When using eventlet, it is important to monkey_patch so I/O does not
# hang.  When using the "threading" model, long polling is used instead of
# WebSockets, and its performance is a bit lower
socketio = SocketIO(async_mode="eventlet")

# Import any modules that refer to socketio here (after socketio has been
# created)
# from . import playbooks
