..
 (c) Copyright 2017 SUSE LLC

=================================
Ardana-Server (Lifecycle Manager)
=================================

REST Service to interact with the Ardana Lifecycle Manager.


Getting started
---------------
Start the server with::

    tox -e runserver

This will setup the environment including cloning necessary playbooks, templates,
and models, and it will install the configuration processor (all in the ``data``
directory).

It will listen on port 9085.

You can verify that it is running properly by using::

    curl http://localhost:9085/api/v2/heartbeat

which will return the current epoch time
