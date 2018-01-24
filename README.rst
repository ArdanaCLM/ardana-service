..
 (c) Copyright 2017 SUSE LLC

=================================
Ardana-Server (Lifecycle Manager)
=================================

REST Service to interact with the Ardana Lifecycle Manager.


Getting started
---------------
Start the service with::

    tox -e runserver

This will setup the environment including cloning necessary playbooks, templates,
and models, and it will install the configuration processor (all in the ``data``
directory).

If when ``tox`` is setting up the environment you get an error like this::

    No package 'libffi' found
    c/_cffi_backend.c:2:20: fatal error: Python.h: No such file or directory
    #include <Python.h>
    ^
    compilation terminated.
    error: Setup script exited with error: command 'gcc' failed with exit status 1

then you should install the packages ``python-devel`` (``python-dev`` on
debian-based distributions) and ``python-cffi``.

When ``tox`` has completed setting up the environment, the ardana service will be
listening on port 9085.

You can verify that it is running properly by using::

    curl http://localhost:9085/api/v2/heartbeat

which will return the current epoch time


Debugging
---------

There are a couple of ways to run this application in a debugger:

    * If you are using PyCharm, you can go to

        File -> Settings

        Build, Execution, Deployment -> Python Debugger

        Tick/check the "Gevent compatible" checkbox

    * If your IDE does not support Gevent-compatible debugging, you can
      temporarily edit ``ardana_service/__init__.py``, changing the line
      containing::

            monkey_patch()

      to::

            monkey_patch(os=False, socket=True)
