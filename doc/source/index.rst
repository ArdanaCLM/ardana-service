..
 (c) Copyright 2017 SUSE LLC

Ardana Service documentation
============================

.. toctree::
   :caption: Table of Contents
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

**Available Endpoints**

=================================== ======== ====================================================================================== 
 Endpoint                            METHOD   Description                                                                           
=================================== ======== ====================================================================================== 
 ``/version``                        GET      Returns version and git commit information about the currently deployed HLM API,      
                                              for example: "0.1.6"
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/heartbeat``                      GET      Returns a the current epoch (seconds since 1970-01-01 00:00:00 GMT)                    
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/templates``                      GET      Return list of the available examples (cloud types) from the examples folder.         
                                              e.g. entry-scale-kvm-vsa, entry-scale-swift...                                        
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/templates/{id}``                 GET      Returns the Input Model for the specified example.                                         
                                              Reads in YAML files from the selected example and returns them as a unified JSON       
                                              object.                                                                               
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/config_processor``               POST     Runs the config processor synchronously (directly runs the python script, not the     
                                              playbook). This is useful for validating the current input model.                     
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/playbooks``                      GET      List Ansible playbooks we can run. In addition    to site ready_deployment and
                                              config_processor_run, all playbooks that don't start with '_' are available.                                                      
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/playbooks/{playbook}``           POST     Create and start an ansible-playbook process for the playbook specified.              
                                              Supported playbooks are listed and described in a GET to /playbooks                   
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/plays``                          GET      List metadata about all ansible plays (live and finished). Limit number of returned 
                                              results with query parameters: ``maxNumber=<N>`` and/or ``maxAge=<seconds>``. If
                                              only live plays are desired use the parameter ``live=true``

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/plays/{pref}``                   GET      Get metadata about the specified ansible play reference.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/plays/{pref}/log``               GET      Gets the log for the specified ansible play reference.
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/plays/{pref}``                   DELETE   Kills the ansible play process identified by the specified process reference if 
                                              it is active.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model``                          GET      Returns the current Input Model. The returned JSON include metadata about the model
                                              as well as the Input Model data.
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/is_encrypted``             GET      Indicates whether the readied config processor output was encrypted or not.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model``                          POST     Replaces the input model on disk with the supplied JSON. The provided JSON is 
                                              analyzed and written back to disk using the same file YAML structure as when
                                              reading (as far as this is possible).  Note that the entire model is re-written
                                              by this operation. The payload required for this POST to work should match what
                                              was returned by a GET to ``/model``
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/state``                    GET      Gets a state representing the current state of the input model This state relates 
                                              to git status, possible states are:

                                              * clean
                                              * modified
                                              * committed
                                              * modifiedAndCommitted
                                              * incorrectHead

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/history``                  GET      Gets the history of the model from the git commit log.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/commit``                   POST     Commits the current input model changes to the git repository.  The request body is
                                              used as the commit message.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/changes``                  DELETE   Resets (cleans) the input model. This performs a git reset, which resets the input
                                              model to the last git commit.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities``                 GET      List top-level configuration entities currently in the input model e.g. servers,
                                              disk-models, networks, server-roles etc. and associated valid sub-routes
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}``        GET      Get a whole entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}``        PUT      Replace a whole entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}``        POST     Add an entry to an array-type entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}/{id}``   GET      Get an individual entry by ID (name or index) from an array-type entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}/{id}``   PUT      Update an individual entry by ID (name or index) from an array-type entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/entities/{entity}/{id}``   DELETE   Delete an individual entry by ID (name or index) from an array-type entity
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/files``                    GET      List yaml files in the model
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/files/{path}``             GET      Get the contents of the given model file
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/files/{path}``             POST     Replace the contents of the given model file with the request body
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/cp_output``                GET      Returns an object with a key for each of the info files in the config processor 
                                              output.  The value of each entry is null.  If the ready query parameter is specified
                                              (e.g. ?ready=true) we look in the "ready" directory instead.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/cp_output/{path}``         GET      Returns the file contents of the indicated file as JSON if a YAML file was 
                                              successfully parsed or as plain text otherwise.  If the ready query parameter is
                                              specified (e.g. ?ready=true) we look in the "ready" directory instead.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/config/{path}``            GET      List config entities available in the customer's config directory. A path can be
                                              specified to drill down into the filesystem. Returns a JSON tree of editable
                                              entities. If path is not specified you get the entire config tree, else you get
                                              the subtree rooted at path. If the path reaches a a leaf you get the file
                                              contents as plain text.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/model/config/{path}``            PUT      Update a config entity in the customer's config directory. The path to the editable
                                              entity must be specified. The body must be directly the new text for the file
                                              (no envelope).  An example path would be glance/glance_api_conf_j2. See the
                                              Postman collection for real examples. Note that this will result in a model
                                              change that needs to committed and readied.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/osinstall``                      POST     Start installation of OS on specified nodes. Details provided in request body.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/osinstall``                      GET      Get status of OS installation for all servers having the OS installed.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers``                        GET      Get the portions of the inputModel that contain servers, including baremetal servers

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers``                        POST     Add a new server to the model after validating that it has the necessary attributes 
                                              (id, ip address, role) and that it does not already exist.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers{id}``                    DELETE   Delete the server from the input model

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers{id}``                    PUT      Update a server in the inputModel.  This effectively deletes and re-adds the server

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers/process``                POST     Add a new server, commit the model, run the config process, ready deployment, and
                                              deploy the server.

                                              **Not yet implemented**
----------------------------------- -------- -------------------------------------------------------------------------------------- 
 ``/servers/{id}/process``           DELETE   Delete the server and deactivate it using the appropriate playbook(s)

                                              **Not yet implemented**
=================================== ======== ====================================================================================== 
                                                                                                                              

REST Details
^^^^^^^^^^^^

Input Model Templates
"""""""""""""""""""""


.. automodule:: ardana_service.templates
    :members:


Validating the input model
""""""""""""""""""""""""""

.. automodule:: ardana_service.config_processor
    :members:


WebSocket API
-------------

The web socket API provides the log-file streaming capability.

