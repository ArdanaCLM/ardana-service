..
 (c) Copyright 2017 SUSE LLC

==========
Deployment
==========

Initial Configuration
---------------------

Standalone Deployment
^^^^^^^^^^^^^^^^^^^^^
The Ardana Lifecycle Manager Service will be delivered with the installer bits.  An
ansible playbook, deployer-init, is employed to set up the deployer which,
among man other things, calls the dayzero-deploy playbook to start up the installer
UI and its related services including the Ardana Service. In its initial configuration,
the Ardana Service will perform no authorization; there are no credentials required
to start or run the installer, nor to perform REST calls to the Ardana Service

In this scenario, the installer UI and the Ardana Service are listening only on the
loopback network interface and thus they will only be accessible to someone that has
logged into the system; therefore the UI is secured behind operating system credentials.

Integrated Deployment
^^^^^^^^^^^^^^^^^^^^^
When integrated with SUSE manager, the installer user interface will be installed
within the SUSE Manager UI, and the Ardana Service will also be started and listening
only on the loopback interface.  Therefore the only way to make calls to the Ardana
are either through the SUSE manager UI, which is secured by its own authentication controls,
or by directly by someone that has logged into the operation system, which is secured
behind operation system credentials.

Deployed Configuration
----------------------

Ardana is deployed by running the ansible "site" playbook.  This playbook
sets up the Ardana Service in its final "deployed" configuration, where it
authenticates using Keystone in much the same way that all other OpenStack services do.  The
ansible playbook for deploying the Ardana Service will run a re-configuration playbook
that updates the Ardana Service configuration with the newly-installed Keystone endpoint
and restart the service.
