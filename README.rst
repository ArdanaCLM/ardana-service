=================================
Ardana-Server (Lifecycle Manager)
=================================

REST Service to interact with the Ardana Lifecycle Manager.


Getting started
---------------

In order to provide meaningful data for development, run the script::

   tools/setup_env.sh

which will setup directories and clone the repositories containing playbooks,
templates, and models into the ``data`` directory

Then start the server with::

    tox -e runserver

it will listen on port 9085.  
You can verify that it is running properly by using::

    curl http://localhost:9085/api/v2/heartbeat

which will return the current epoch time
