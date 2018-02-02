..
 (c) Copyright 2017-2018 SUSE LLC

Input Model
===========
This describes the structure of the input model, which has two related
representations: the on-disk format, and the JSON format used the the ardana
service API.

On-Disk Format
--------------
When stored on disk, the input model is simply one or more files which may be
stored in a nested directory structure.  The one hard requirement is that the
top level must contain the file ``cloudConfig.yml``.

The convention that most input models follow is that ``cloudConfig.yml`` is the
only YAML file at the top level of the tree, and a ``data`` subdirectory
contains all of the other files and nested subdirectories.

There are two types of files:

- a README file 

  This can have an optional suffix, and the file contents are simply loaded
  verbatim

- YAML files

  All other files in the model are formatted as conventional block-formatted
  YAML.


Each YAML file contains a dictionary at the top level.  The entries in this
dictionary will either be dictionaries or lists.

Dictionary Entries
~~~~~~~~~~~~~~~~~~
All dictionaries are required to be unique across all files in the model with
two exceptions: ``product`` and ``pass-through``:

- ``product``

    Each file will contain the following entry::

        product:
            version: 2

- ``pass-through``

    This special dictionary may appear in more than one data model yaml file.
    But the uniqueness constraint is pushed down one or two levels on this item:
    if ``pass-through`` contains a nested dictionary, either its name must be
    unique, or it contains another nested dictionary, those keys must be
    unique.  For example, ``pass-through-1.yml`` could contain::

        pass-through:
            global:
                foo: fooey

    while ``pass-through-2.yml`` could contain::

        pass-through:
            global:
                bar: baz

    since the concatenated sub-key ``global.foo`` is different from ``global.bar``.


All other dictionaries are unique across all files in the model.  For example,
``cloudConfig.yml`` contains the entry::

   cloud:
     name: padawan
     ...

and thus no other file in the data model contains a ``cloud`` dictionary at the
top level.

It is worth noting that dictionaries and lists may be nested many levels, and the
uniqueness constraint does not apply beyond the top level.  In other words, two
different dictionaries may both contain a ``tags`` dictionary without being in
conflict.


List Entries
~~~~~~~~~~~~
All other top-level entries in YAML dictionaries are lists of dictionaries.
Each dictionary in the list must have a key field, which is one of: ``name``,
``id``, ``region-name``, ``node_name``.  Most of these top-level dictionary keys
appear in only one file.  For example, the ``firewall-rules`` dictionary
normally appears only in the ``data/firewall_rules.yml`` file.

.. _`disk-model-example`:

Some dictionaries can be spread across multiple file, provided that their key
fields are unique.  The most common example of this is disk models.  For
example, the file ``data/disks_compute.yml`` may contain::

   disk-model:
   - name: COMPUTE-DISKS
     ...

while ``data/disk_controller_1TB.yml`` may contain::

   disk-model:
   - name: CONTROLLER-1TB-DISKS
     ...


JSON Layout
-----------
The REST API combines the entire data model into a single JSON dictionary.  It
has two main sections:

- ``inputModel``

    This is the combined data model.  The entries from the individual YAML files
    are entered as nested entries in ``inputModel``.  For those entries that are
    can be non-unique (``pass-through`` and  lists), they are merged together
    into the combined data model.  For example, the various ``disk-model`` list
    elements from the various files are combined into a single list.

- ``fileInfo``

    This is basically an index that maps each element in the combined
    ``inputModel`` to the filename from which it was loaded.  Its structure is
    detailed in `fileInfo contents`_

It is important to understand that the ``fileInfo`` section is intended to be
an opaque implementation detail of the ardana service; in other words, APIs that
receive and manipulate this large JSON structure should not rely on the format
of ``fileInfo``, and more importantly, should not manipulate it in any way.


fileInfo contents
-----------------
The ``fileInfo`` section of the JSON model currently contains nested
dictionaries:

- ``fileSectionMap``

    This dictionary contains an entry for every file, whose value is a list of
    sections that appear in the file.  For those sections that may not be
    unique in the input model, it contains key information to indicate which
    entries can from that particular file.  More details are in the next
    section.

- ``files``

  Simple list of files that were part of this input model.  This section is
  redundant since it can be easily derived from the contents of
  ``fileSectionMap``.  Thus it should be removed from ``fileInfo``.

- ``sections``

  Dictionary that maps a section name to the list of files that contain it.
  For example::
    
    "control-planes": [
       "data/control_plane.yml"
    ]

  Like the ``files`` section, this one is also redundant with ``fileSectionMap``
  and should be removed.


``fileInfo`` / ``fileSectionMap`` contents
------------------------------------------
The purpose of this section is to uniquely identify the file from which every
single piece of information in the ``inputModel`` was loaded.  Its purpose is to
enable the REST call that writes the model to disk to write back the changes to
the appropriate original file.  It also uses this to detect when new files need
to be created or old ones need to be deleted.
  
The ``fileSectionMap`` dictionary contains an entry for every file with a list
of sections in the file including any necessary key information needed to
uniquely identify the data.  Here is the simple version that is typical for
``cloudConfig.yml``, showing that is has ``product`` and ``cloud`` sections::

    "fileInfo": {
        "fileSectionMap": {
            "cloudConfig.yml": [
                "product",
                "cloud"
            ],
        }
    }


The format of a section in the ``fileSectionMap`` depends on whether the data
contains a dictionary or list.

Dictionary Section
~~~~~~~~~~~~~~~~~~
As discussed above, dictionary names are required to be unique across the entire
input model, with the exception of ``product`` and ``pass-through``.  Therefore
for all dictionaries other than ``pass-through`` (discussed in the next
paragraph), the section in the ``fileSectionMap`` contains just the name of the
dictionary.  That is the case for the ``cloudConfig.yml`` in the previous
example , which contains the nested dictionaries ``product`` and ``cloud``.

If only one file in the model has a ``pass-through`` dictionary, then it too
will simply have the dictionary name in the ``fileSectionMap``::

    "fileSectionMap": {
        "data/pass_through.yml": [
            "product",
            "pass-through"    # NOTE: No detailed info here, just a name
        ],
        ...

But if there are more multiple files with a ``pass-through`` dictionary, then it
becomes more complicated: each section in the map has to contain additional info
to capture which parts of the model came from which files.  Here is an example
where two files, ``data/cp_pass_through.yml`` and ``data/pass_through.yml`` both
have a ``pass-through`` dictionary.  Instead of just the ``pass-through`` string
(as above), section now has a dictionary containing ``"type": "object"`` and a
``pass-through`` element that contains a list of keys.  For example, these
files:

- ``data/cp_pass_through.yml``::

   product:
     version: 2
   pass-through:
    global:
      esx_cloud: true

- ``data/pass_through.yml`` ::

   product:
     version: 2
   pass-through:
    global:
      lib_mysql_java_file_name: libmysql-java_5.1.32-1_all.deb
      thirdparty_folder-env: /home/stack/stage/thirdparty


would be represented by this::

    "fileInfo": {
        "fileSectionMap": {
            "data/cp_pass_through.yml": [
                "product",
                {                           # <- A structure rather than a name
                    "type": "object",
                    "pass-through": [       # <- A list of keys
                        "global.esx_cloud"  # <-    with dots to show nesting
                    ]
                }
            ],
            "data/pass_through.yml": [
                "product",
                {
                    "type": "object",
                    "pass-through": [
                        "global.thirdparty_folder-env",
                        "global.lib_mysql_java_file_name",
                    ]
                }
            ]}},
    "inputModel": {
        "pass-through": {
            "global": {
                "esx_cloud": true,
                "lib_mysql_java_file_name": "libmysql-java_5.1.32-1_all.deb",
                "thirdparty_folder-env": "/home/stack/stage/thirdparty"
            }
        },
    }

Note how the keys from the nested ``global`` dictionary like
``global.esx_cloud`` are joined with dots.  This is special to ``pass-through``
dictionaries -- two files can contain dictionaries with the same names (e.g. ``global``), 
as long as their nested entries have unique keys.


List Section
~~~~~~~~~~~~
Most input model files dictionaries contain lists of dictionaries.  For
example ``data/networks.yml`` might contain::

    "networks": [
            {
                "cidr": "192.168.10.0/24",
                "gateway-ip": "192.168.10.1",
                "name": "HLM-NET",
                "network-group": "HLM",
                "tagged-vlan": false,
                "vlanid": 101
            },
            {
                "cidr": "192.168.245.0/24",
                "gateway-ip": "192.168.245.1",
                "name": "MANAGEMENT-NET",
                "network-group": "MANAGEMENT",
                "tagged-vlan": false,
                "vlanid": 102
            },

The corresponding ``fileSectionMap`` section would be::

    "fileSectionMap": {
        "data/networks.yml": [
            "product",
            {
                "type": "array",
                "keyField": "name",
                "networks": [
                   "HLM-NET",
                   "MANAGEMENT"
                ]
            }
        ],

Since each ``fileSectionMap`` section explicitly lists which keys appear in
which file, this will naturally support dictionaries being spread across
multiple files.  The relevant portion of the ``fileSectionMap`` for the
`disk-model-example`_ would be::

    "data/disks_compute.yml": [
        "product",
        {
            "type": "array",
            "keyField": "name",
            "disk-models": [
                "COMPUTE-DISKS"
            ]
        },
    ],
    "data/disks_controller_1TB.yml": [
        "product",
        {
            "type": "array",
            "keyField": "name",
            "disk-models": [
                "CONTROLLER-1TB-DISKS"
            ]
        }
    ]


Conventions for new data
------------------------
When an input model whose ``inputModel`` contains items that do not correspond
to any entries in the ``fileSectionMap`` is POSTed to the REST interface, the
ardana service will follow several conventions.  These conventions are not
strict rules require by the model, but they are useful to know when running the
service or trying to understand the code.  There are a number of cases to
consider:

new dictionary or list

    If a new dictionary or list appears in the ``inputModel``, then the entire
    dictionary or list is written to a new file in the ``data`` directory of the
    model.  The file's name will be the name of the dictionary or list, with dash
    characters replaced with underscores.

new entries in existing dictionary

    Except for ``pass-through`` (next item) and ``product`` (which is static),
    all dictionaries are contained in a single file.  New entries in an existing
    dictionary will be written to that same file.

new entries in ``pass-through`` dictionary

    All new entries in an existing ``pass-through`` dictionary will be written
    to a single (common) new file, named ``data/pass_through_XXXXXXXX.yml``,
    where ``XXXXXXXX`` are random hex digits.

new entries in single-file list

    If one or more new entries appears in an existing list that previously was
    contained in a single file, then all new entries will be written to that
    same file.

new entries in split-file list

    If new entries appear in a list that was currently distributed across
    several files, like the `disk-model-example`_, then one of two situations
    arises:

    - If there is a 1-1 mapping between list entries and file (i.e. all of the
      files that contain entries in the list has exactly one entry), then each
      new entry will be written to a separate file in the ``data`` directory,
      whose name will be derived from the key name.

    - Otherwise (there was not a 1-1 mapping between list entries and files),
      then all new entries will be written to a single (common) file in the
      ``data`` directory, whose name will be derived from the one of the key
      names.
