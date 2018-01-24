..
 (c) Copyright 2017 SUSE LLC


REST API
--------

The REST API:

* Reads and makes available the input model to clients (both the current state of the file system and the output from ready-deploy)

* Allows updates to be made to the input model (while retaining the on-disk file structure used as far as possible)

* Allows the input model git repository to be manipulated (e.g commit changes, reset to last commit)

* Invokes the config processor

* Invokes selected ansible playbooks

* Manages log files associated with config processor and ansible playbook runs, gives access to these and streams these incrementally via web sockets, to allow clients to efficiently show log files

**Available Endpoints**

.. qrefflask:: ardana_service.main:app
    :order: path

**Changed for v2**

The following endpoints were changed:

* ``/model/config/{path}`` was changed to ``/service/files/{path}`` to more accurately reflect that fact that the
  endpoint manages service config files rather than model files.

The following endpoints were removed:

* ``/servers`` for updating the input model. This functionality can be performed by using the ``/model`` endpoints

* ``/servers/process``, which combined several REST calls into a single endpoint.  The
  individual REST calls (to commit the model, run the config processor, and launch playbooks) must be called individually.

* ``/osinstall`` , which called several ansible playbooks.  Callers instead should use the
  ``/playbooks`` endpoint to run a single ansible playbook that in turn executes all of these same tasks, such as
  ``dayzero-os-provision.yml``.

* ``/model/expanded``. The ``/model/cp_output`` can be used instead to obtain the same information

* ``/model/history``. This was not being used by any client.

Other changes to existing endpoints are documented in the details of each endpoint.


REST Details
^^^^^^^^^^^^

.. autoflask:: ardana_service.main:app
    :endpoints:
    :order: path


SocketIO API
------------

The socketIO API provides the log-file streaming capability.  The Ardana Service accepts SocketIO
connections to the same port as its REST interface (``9085`` by default).  While a play is
alive, the service will emit an event for each message received from the running playbook on
a room whose name is the play ``id``.  A socketIO client can join the room and expect a
read these messages.

The following is an example program that illustrates calling a playbook, and
openeng up a socketIO connection to capture and display its output in real-time:

.. include:: ../../test_socketio_client.py
    :literal:
