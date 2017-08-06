..
 (c) Copyright 2017 SUSE LLC

Ardana Service documentation
============================

Contents:

.. toctree::
   :maxdepth: 2
   :glob:

   readme

REST API
--------

The REST API:

* Reads and makes available the input model to clients (both the current state of the file system and the output from ready-deploy)

* Allows updates to be made to the input model (while retaining the on-disk file structure used as far as possible)

* Allows the input model git repository to be manipulated (e.g commit changes, read commit history)

* Invokes the config processor

* Invokes selected ansible playbooks

* Manages log files associated with config processor and ansible playbook runs, gives access to these and streams these incrementally via web sockets, to allow clients to efficiently show log files


.. automodule:: ardana_service.templates
    :members:


WebSocket API
-------------

The web socket API provides the log-file streaming capability.

