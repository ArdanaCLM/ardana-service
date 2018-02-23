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

import collections
import copy
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import url_for
import os
from oslo_config import cfg
from oslo_log import log as logging
import random
import yaml


LOG = logging.getLogger(__name__)

CLOUD_CONFIG = "cloudConfig.yml"

bp = Blueprint('model', __name__)
CONF = cfg.CONF

# Define some constants to avoid problems caused by typos
CHANGED = 'changed'
IGNORED = 'ignored'
DELETED = 'deleted'
ADDED = 'added'

PASS_THROUGH = 'pass-through'


@bp.route("/api/v2/model", methods=['GET'])
def get_model():
    """Returns the current input model.

    .. :quickref: Model; Returns the current input model

    The returned JSON include metadata about the model as well as the Input
    Model data.

    :status 200: when model is succesfully read, parsed, and returned
    :status 404: failure to find or read model
    """
    try:
        return jsonify(read_model())
    except IOError:
        abort(404)


@bp.route("/api/v2/model", methods=['POST'])
def update_model():
    """Replace the input model with the supplied JSON.

    The provided JSON is analyzed and written back to disk using the same file
    YAML structure as when reading (as far as this is possible). Note that the
    entire model is re-written by this operation. The payload required for this
    POST to work should match what was returned by :http:get:`/api/v2/model`

    .. :quickref: Model; Update the current input model

    :status 200: when model is succesfully written
    :status 400: failure to find or read model
    """
    model = request.get_json() or {}
    try:
        write_model(model)
        return 'Success'
    except Exception:
        abort(400)


@bp.route("/api/v2/model/entities", methods=['GET'])
def get_entity_operations():
    """List top-level entities in the input model

    List top-level configuration entities currently in the input model e.g.
    servers, disk-models, networks, server-roles etc. and associated valid
    sub-routes.

    .. :quickref: Model; List top-level entities in the input model

    """

    model = read_model()
    entity_operations = {}
    for key, val in model['inputModel'].iteritems():
        ops = {}
        ops['get'] = 'GET ' + \
            url_for('model.get_entities', entity_name=key)
        ops['update'] = 'PUT ' + \
            url_for('model.update_entities', entity_name=key)

        if isinstance(val, list):
            ops['add'] = 'POST ' + \
                url_for('model.create_entity', entity_name=key)
            ops['getById'] = 'GET ' + \
                url_for('model.get_entity_by_id', entity_name=key, id=':id')
            ops['updateById'] = 'PUT ' + \
                url_for('model.update_entity_by_id', entity_name=key, id=':id')
            ops['deleteById'] = 'DELETE ' + \
                url_for('model.delete_entity_by_id', entity_name=key, id=':id')

        entity_operations[key] = ops

    return jsonify(entity_operations)


@bp.route("/api/v2/model/entities/<entity_name>", methods=['GET'])
def get_entities(entity_name):
    """Get a whole entity

    .. :quickref: Model; Get a whole entity

    :param entity_name: name of the entity
    :status 200: success
    :status 404: failure to read model or find the given entity
    """

    model = read_model()
    try:
        return jsonify(model['inputModel'][entity_name])
    except KeyError:
        abort(404)


@bp.route("/api/v2/model/entities/<entity_name>", methods=['PUT'])
def update_entities(entity_name):
    """Replace a whole entity by name.

    .. :quickref: Model; Replace a whole entity in the input model

    :param entity_name: Name of the entity
    """

    model = read_model()
    if entity_name not in model['inputModel']:
        abort(404)
    new_entity = request.get_json()

    model['inputModel'][entity_name] = new_entity
    write_model(model)
    return 'Success'


def get_entity_index(entities, id):
    # Find the index of the given id in the entities list
    try:
        key_field = get_key_field(entities[0])
        for index, e in enumerate(entities):
            if e[key_field] == id:
                return index
        else:
            abort(404)

    except (KeyError, IndexError):
        abort(404)


@bp.route("/api/v2/model/entities/<entity_name>/<id>", methods=['GET'])
def get_entity_by_id(entity_name, id):
    """Get an individual entry by id (name or index) from an array-type entity

    .. :quickref: Model; Get an individual entity from the input model

    :param entity_name: name of the entity
    :param id: id of the individual entity
    :status 200: success
    :status 404: failure to read model or find the given entity
    """

    model = read_model()
    try:
        entities = model['inputModel'][entity_name]
        index = get_entity_index(entities, id)
        return jsonify(entities[index])

    except (KeyError, IndexError):
        abort(404)


@bp.route("/api/v2/model/entities/<entity_name>/<id>", methods=['PUT'])
def update_entity_by_id(entity_name, id):
    """Update an individual entry by id

    Update an individual entry by id (name or index) from an array-type entity.

    .. :quickref: Model; Update an individual entity in the input model

    :param entity_name: Name of the entity
    :param id: id of the individual entity
    """

    model = read_model()
    new_entity = request.get_json()
    try:
        entities = model['inputModel'][entity_name]
        index = get_entity_index(entities, id)
        entities[index] = new_entity
        write_model(model)
        return 'Success'

    except (KeyError, IndexError):
        abort(404)


@bp.route("/api/v2/model/entities/<entity_name>/<id>", methods=['DELETE'])
def delete_entity_by_id(entity_name, id):
    """Delete an individual entry by id

    Delete an individual entry by ID (name or index) from an array-type entity

    .. :quickref: Model; Delete an individual entry by id

    :param entity_name: Name of the entity
    :param id: id of the individual entity
    """
    model = read_model()
    try:
        entities = model['inputModel'][entity_name]
        index = get_entity_index(entities, id)
        del(entities[index])
        write_model(model)
        return 'Success'

    except (KeyError, IndexError):
        abort(404)


@bp.route("/api/v2/model/entities/<entity_name>", methods=['POST'])
def create_entity(entity_name):
    """Add an entry to an array-type entity

    .. :quickref: Model; Add an entry to an array-type entity

    :param entity_name: Name of the entity
    """
    model = read_model()
    new_entity = request.get_json()

    key_field = get_key_field(new_entity)
    entities = model['inputModel'][entity_name]
    try:
        # Make sure it does not already exist
        for e in entities:
            if e[key_field] == new_entity[key_field]:
                abort(400)
    except (KeyError, IndexError):
        abort(404)

    entities.append(new_entity)
    write_model(model)
    return 'Success'


@bp.route("/api/v2/model/files", methods=['GET'])
def get_all_files():
    """List yaml files in the model

    .. :quickref: Model; List yaml files in the model
    """

    file_list = []

    # Establish descriptions for those files that are shipped in any of the
    # templates
    well_known_files = {
        'cloudConfig': 'Cloud Configuration',
        'control_plane': 'Control Planes',
        'designate_config': 'Designate Configuration',
        'disks_compute': 'Disks (Compute)',
        'disks_control_common_600GB': 'Disks (600GB Control Common)',
        'disks_controller_1TB': 'Disks (1TB Controller)',
        'disks_controller_600GB': 'Disks (600B Controller)',
        'disks_dbmq_600GB': 'Disks (600GB DB/MQ)',
        'disks_hlinux_vm': 'Disks (VM)',
        'disks_mtrmon_2TB': 'Disks (2TB MML)',
        'disks_mtrmon_4.5T': 'Disks (4.5TB MML)',
        'disks_mtrmon_600GB': 'Disks (600GB MML)',
        'disks_osd': 'Disks (OSD)',
        'disks_rgw': 'Disks (RGW)',
        'disks_swobj': 'Disks (SWOBJ)',
        'disks_swpac': 'Disks (SWPAC)',
        'disks_vsa': 'Disks (VSA)',
        'firewall_rules': 'Firewall Rules',
        'ironic_config': 'Ironic Configuration',
        'net_interfaces': 'Network Interfaces',
        'network_groups': 'Network Groups',
        'networks': 'Networks',
        'neutron_config': 'Neutron Configuration',
        'nic_mappings': 'NIC Mappings',
        'octavia_config': 'Octavia Configuration',
        'pass_through': 'Pass-through',
        'server_groups': 'Server Groups',
        'server_roles': 'Server Roles',
        'servers': 'Servers',
        'swift_config': 'Swift Configuration',
    }

    # Now read and process all yml files in the dir tree below
    for root, dirs, files in os.walk(CONF.paths.model_dir):
        for file in files:
            relname = os.path.relpath(os.path.join(root, file),
                                      CONF.paths.model_dir)
            if file.endswith('.yml'):

                basename = os.path.basename(relname).split('.')[0]

                description = well_known_files.get(basename)
                if not description:
                    # As a fallback the description will be just use the
                    # filename (without extension) using space in place of
                    # underscores
                    description = basename.replace('_', ' ')

                file_list.append({
                    'name': relname,
                    'description': description
                })

    return jsonify(file_list)


@bp.route("/api/v2/model/files/<path:name>", methods=['GET'])
def get_model_file(name):
    """Get the contents of the given model file

    .. :quickref: Model; Get the contents of the given model file

    :param path: name of the file
    """
    filename = os.path.join(CONF.paths.model_dir, name)
    contents = ''
    try:
        with open(filename) as f:
            lines = f.readlines()
        contents = contents.join(lines)

    except IOError as e:
        LOG.exception(e)
        abort(400)

    return jsonify(contents)


@bp.route("/api/v2/model/files/<path:name>", methods=['POST'])
def update_model_file(name):
    """Update the contents of the given model file

    .. :quickref: Model; Update the contents of the given model file

    :param path: name of the file
    """
    data = request.get_json()

    # Verify that it is valid yaml before accepting it
    try:
        yaml.safe_load(data)
    except yaml.YAMLError:
        LOG.exception("Invalid yaml data")
        abort(400)

    # It's valid, so write it out
    filename = os.path.join(CONF.paths.model_dir, name)
    try:
        with open(filename, "w") as f:
            f.write(data)
        return 'Success'
    except Exception as e:
        LOG.exception(e)
        abort(400)


@bp.route("/api/v2/model/is_encrypted")
def get_encrypted():
    """Returns whether the readied config processor output is encrypted.

    .. :quickref: Model; Returns whether the config processor output is encrypted

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
           "isEncrypted": false
       }

    :status 200: success
    :status 404: if the config processor has not been run
    """

    VAULT_MARKER = '$ANSIBLE_VAULT'
    try:
        vault_file = os.path.join(CONF.paths.playbooks_dir, 'group_vars',
                                  'all')
        with open(vault_file) as f:
            marker = f.read(len(VAULT_MARKER))
        encrypted = (marker == VAULT_MARKER)
        return jsonify({"isEncrypted": encrypted})

    except Exception as e:
        LOG.exception(e)
        abort(404)


@bp.route("/api/v2/model/cp_output")
def list_cp_output():
    """Lists the config processor output files

    :query ready: ``true`` to return the file from the "ready" directory.

    **Changed for v2**:

    The return from this structure is a list of filenames rather than an object
    with null values and keys containing filenames without extensions.

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
           "address_info.yml",
           "control_plane_topology.yml",
           "firewall_info.yml",
           "net_info.yml",
           "network_topology.yml",
           "region_topology.yml",
           "route_info.yml",
           "server_info.yml",
           "service_info.yml",
           "service_topology.yml"
       ]

    .. :quickref: Model; Lists the config processor output files
    """

    if request.args.get("ready") == "true":
        output_dir = CONF.paths.cp_ready_output_dir
    else:
        output_dir = CONF.paths.cp_output_dir

    try:
        results = [name for name in os.listdir(output_dir)
                   if name.endswith(".yml")]
        return jsonify(results)
    except OSError:
        LOG.error("Unable to read %s directory", output_dir)
        abort(404)


@bp.route("/api/v2/model/cp_output/<path:name>")
def get_cp_output_file(name):
    """Returns the contents of a file from the config processor output directory

    Returns the content as JSON.

    .. :quickref: Model; Returns the contents of a file from the config processor output directory

    :query ready: ``true`` to return the file from the "ready" directory.

    :param path: name of the file

    **Changed for v2**:

    This function will accept filenames with or without the .yml extension.
    The contents are always returned as JSON.

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/model/cp_output/address_info.yml?ready=true HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
           "EXTERNAL-API": {
               "EXTERNAL-API-NET": {
                   "192.168.14.2": [
                       "helion-ccp-c1-m1-extapi"
                   ],
                   "192.168.14.3": [
                       "helion-ccp-c1-m2-extapi"
                   ],
                   "192.168.14.4": [
                       "helion-ccp-c1-m3-extapi"
                   ],
                   "192.168.14.5": [
                       "helion-ccp-vip-public-CEI-API-extapi",
                       "... and so on"
                   ]
               }
           }
       }

    **Changes for v2**:

    When requesting a filename, it is deprecated to specify a suffix of
    ``_yml`` and expect it to match a real filename ending with ``.yml``.
    """

    if request.args.get("ready") == "true":
        output_dir = CONF.paths.cp_ready_output_dir
    else:
        output_dir = CONF.paths.cp_output_dir

    filename = os.path.join(output_dir, name).replace("_yml", ".yml")
    if not filename.endswith(".yml"):
        filename += ".yml"

    try:
        with open(filename) as f:
            lines = f.readlines()
        raw = ''.join(lines)

        contents = yaml.safe_load(raw)
        return jsonify(contents)

    except (OSError, IOError):
        LOG.error("Unable to read %s", filename)
        abort(404)

    except yaml.YAMLError:
        # If the generated file is not valid yml, there is some problem with
        # the config processor
        LOG.error("%s is not a valid yaml file", filename)
        abort(500)


#
# Functions to read the model
#

def get_key_field(obj):

    # Several kinds of ids are used in the input model:
    #     id          : used for servers.yml
    #     region-name : used for swift/rings.yml
    #     node_name   : used for baremetalConfig.yml
    #     name        : all others
    # Figure out which one is populated and return it
    if obj:
        for key in ('name', 'id', 'region-name', 'node_name'):
            if key in obj:
                return key


def read_model(model_dir=None):
    """Reads the input model directory structure into a big dictionary

    Reads all of the yaml files from the given directory and loads them into a
    single giant dictionary.  The dictionary includes tracking information to
    capture where each entry was loaded, so that the object can be written back
    out to the appropriate files
    """

    model_dir = model_dir or CONF.paths.model_dir

    # First read and process the top-level cloud config file
    cloud_config_file = os.path.join(model_dir, CLOUD_CONFIG)

    model = {'name': None,
             'version': None,
             'readme': {},
             'fileInfo': {},
             'errors': [],
             }

    with open(cloud_config_file) as f:
        try:
            doc = yaml.safe_load(f)
        except yaml.YAMLError:
            LOG.exception("Invalid yaml file")
            raise
        except IOError:
            LOG.exception("Unable to read yaml file")
            raise

    if not doc:
        return model

    try:
        model['version'] = doc['product']['version']
    except KeyError:
        raise 'Missing cloud config product version'

    try:
        model['name'] = doc['cloud']['name']
    except KeyError:
        raise 'Cloud config error: no name specified'

    relname = CLOUD_CONFIG
    model['fileInfo'] = {
        'configFile': cloud_config_file,
        'directory': model_dir,
        'files': [relname],
        'sections': collections.defaultdict(list),
        'fileSectionMap': collections.defaultdict(list),
        'mtime': int(1000 * os.stat(cloud_config_file).st_mtime),
        '_object_data': collections.defaultdict(list),
    }
    model['inputModel'] = {}

    add_doc_to_model(model, doc, relname)

    # Now read and process all yml files in the dir tree below
    for root, dirs, files in os.walk(model_dir):
        for file in files:
            # avoid processing top-level cloud config again
            if file == CLOUD_CONFIG:
                continue

            relname = os.path.relpath(os.path.join(root, file), model_dir)
            filename = os.path.join(root, file)
            if file.endswith('.yml'):
                model['fileInfo']['files'].append(relname)
                with open(filename) as f:
                    try:
                        doc = yaml.safe_load(f)
                        add_doc_to_model(model, doc, relname)
                    except yaml.YAMLError:
                        LOG.exception("Invalid yaml file")

            elif file.startswith('README'):
                ext = file[7:]
                with open(filename) as f:
                    lines = f.readlines()
                model['readme'][ext] = ''.join(lines)

    # Update metadata related to pass-through, if necessary
    update_pass_through(model)

    return model


def add_doc_to_model(model, doc, relname):

    for section, value in doc.iteritems():
        # Add to fileInfo / sections
        model['fileInfo']['sections'][section].append(relname)

        if isinstance(value, list):
            # Add to fileInfo / fileSectionMap
            key_field = get_key_field(value[0])
            mapping = {
                'keyField': key_field,
                'type': 'array',
                section: [e[key_field] for e in value],
            }
            model['fileInfo']['fileSectionMap'][relname].append(mapping)

            # Add to inputModel
            if section not in model['inputModel']:
                model['inputModel'][section] = []
            model['inputModel'][section].extend(value)

        elif isinstance(value, dict) and section == PASS_THROUGH:
            key_fields = []
            if section not in model['inputModel']:
                model['inputModel'][section] = {}

            for key, val in value.iteritems():

                # if pass-through section contains a nested dictionary, add
                #    each of the keys of that nested dict
                if isinstance(val, dict):
                    key_fields.extend([".".join((key, n)) for n in val.keys()])
                    if key not in model['inputModel'][section]:
                        model['inputModel'][section][key] = {}
                    model['inputModel'][section][key].update(val)
                else:
                    key_fields.append(key)
                    model['inputModel'][section][key] = val

            mapping = {
                PASS_THROUGH: key_fields,
                'type': 'object'
            }
            model['fileInfo']['fileSectionMap'][relname].append(mapping)
        else:
            # primitive, or some dict other than pass-through.
            model['fileInfo']['fileSectionMap'][relname].append(section)
            model['inputModel'][section] = value


def update_pass_through(model):

    # If there is only one file containing pass-through data, then its
    # entry in fileInfo / fileSectionMap should be stripped of its nested keys
    # and become a simple string

    if len(model['fileInfo']['sections'][PASS_THROUGH]) == 1:
        filename = model['fileInfo']['sections'][PASS_THROUGH][0]

        for i, val in enumerate(model['fileInfo']['fileSectionMap'][filename]):
            if isinstance(val, dict) and PASS_THROUGH in val:
                model['fileInfo']['fileSectionMap'][filename][i] = \
                    PASS_THROUGH
                break


#
# Functions to write the model
#

# This function is long and should be modularized
def write_model(in_model, model_dir=None, dry_run=False):  # noqa: C901

    model_dir = model_dir or CONF.paths.model_dir

    # Create a deep copy of the model to avoid munging the model that was
    # passed in
    model = copy.deepcopy(in_model)

    # Keep track of what was written, by creating a dict with this format:
    #    filename: {
    #        data: <data written to file>
    #        status: DELETED | CHANGED | ADDED | IGNORED
    #    }
    # This is mostly used for unit testing (too return what has changed), but
    # some of this information is also used to detect whether a stale file
    # is lingering in the model dir and that needs to be removed
    written_files = {}

    # Write portion of input model that correspond to existing files
    file_section_map = model['fileInfo']['fileSectionMap']
    for filename, sections in file_section_map.iteritems():
        new_content = {}

        # sections is a list of sections in the file
        for section in sections:

            if isinstance(section, basestring):
                # Skip the remaining processing if the entire section has been
                # removed
                if section not in model['inputModel']:
                    continue

                # This section is just a flat name so the section is just the
                # name.  Note that this will process primitive types as well as
                # single-file pass-through's (which contain no details in the
                # map)
                section_name = section

                if section_name == 'product':
                    new_content[section_name] = \
                        model['inputModel'][section_name]
                else:
                    new_content[section_name] = \
                        model['inputModel'].pop(section_name)
            else:
                # This is a dict that either defines an array (i.e. list)
                #   {'type' : 'array'  <-
                #    'keyField' : 'id' (or 'region-name' or 'name', etc.
                #    '<NAME>': [ '<id1>', '<id2>' ]}
                #    where <NAME> is the section name (e.g. disk-models), and
                #    the value of that entry is a list of ids
                #
                # or it contains an entry (i.e. dict) for pass-through:
                #   {'type' : 'object'
                #    'pass-through': ['k1.k2', 'k1.k3', 'k4']   <- dotted keys
                #   }

                section_type = section['type']
                section_name = [k for k in section.keys()
                                if k not in ('type', 'keyField')][0]

                # Skip the remaining processing if the entire section has been
                # removed
                if section_name not in model['inputModel']:
                    continue

                if section_type == 'array':

                    if len(model['fileInfo']['sections'][section_name]) == 1:
                        # This section of the input model is contained in a
                        # single file, so write out all members of this section
                        new_content[section_name] = \
                            model['inputModel'].pop(section_name)

                    else:
                        # This section of the input model is contained in a
                        # several files.  Write out just the portions that
                        # belong in this file

                        # Get the list of ids for this file
                        our_ids = section[section_name]
                        key_field = section.get('keyField')

                        for model_item in model['inputModel'][section_name]:
                            id = model_item.get(key_field)
                            if id in our_ids:
                                if section_name not in new_content:
                                    new_content[section_name] = []
                                new_content[section_name].append(model_item)

                        # Remove these from the model
                        model['inputModel'][section_name] = \
                            [k for k in model['inputModel'][section_name]
                             if k[key_field] not in our_ids]

                else:
                    inputPassThru = model['inputModel'].get(PASS_THROUGH)
                    if not inputPassThru:
                        continue

                    # Pass-throughs that are spread across multiple files
                    for dotted_key in section[PASS_THROUGH]:
                        key_list = dotted_key.split('.')

                        if len(key_list) == 1:
                            # There was no dot, so copy the whole dict over
                            key = key_list[0]

                            if key in inputPassThru:
                                val = inputPassThru.pop(key)

                            if PASS_THROUGH not in new_content:
                                new_content[PASS_THROUGH] = {}
                            new_content[PASS_THROUGH][key] = val
                        else:
                            # There was a dot, so there is a nested dict,
                            # so we have to update any existing one
                            (first, second) = key_list

                            # A try is needed in case first is not in input
                            # model
                            try:
                                if second in inputPassThru[first]:
                                    val = inputPassThru[first].pop(second)

                                    if PASS_THROUGH not in new_content:
                                        new_content[PASS_THROUGH] = {}
                                    if first not in new_content[PASS_THROUGH]:
                                        new_content[PASS_THROUGH][first] = {}

                                    new_content[PASS_THROUGH][first][second] \
                                        = val

                                # Remove the dictionary if it is now empty
                                if not inputPassThru[first]:
                                    inputPassThru.pop(first)

                            except (TypeError, KeyError):
                                pass

        real_keys = [k for k in new_content.keys() if k != 'product']
        if real_keys:
            status = write_file(model_dir, filename, new_content, dry_run)
            written_files[filename] = {'data': new_content, 'status': status}

    # Write portion of input model that remain -- these have not been written
    # to any file
    for section_name, contents in model['inputModel'].iteritems():
        # Skip those sections that have been entirely written and removed
        if not contents:
            continue

        # Skip the special 'product' section
        if section_name == 'product':
            continue

        data = {'product': model['inputModel']['product']}

        basename = os.path.join('data', section_name.replace('-', '_'))

        if section_name not in model['fileInfo']['sections']:
            # brand new section
            filename = basename + '.yml'

            data[section_name] = contents
            status = write_file(model_dir, filename, data, dry_run)
            written_files[filename] = {'data': data, 'status': status}

        elif isinstance(contents, list):

            key_field = get_section_key_field(model, section_name)
            if is_split_into_equal_number_of_files(model, section_name):
                # each entry in the list should be written to a separate file,
                # so create new files for each section
                for elt in contents:
                    data[section_name] = [elt]

                    filename = "%s_%s.yml" % (basename, elt[key_field])
                    status = write_file(model_dir, filename, data, dry_run)
                    written_files[filename] = {'data': data, 'status': status}
            else:
                # place all elements of the list into a single file
                data[section_name] = contents
                filename = "%s_%s.yml" % (basename,
                                          contents[0][key_field])
                status = write_file(model_dir, filename, data, dry_run)
                written_files[filename] = {'data': data, 'status': status}
        else:
            # Not a list, so therefore it must be pass-through data that did
            # correspond to known any existing passthrough file. All remaining
            # entries should be written to a single file
            data[section_name] = contents
            filename = "%s_%s.yml" % (basename,
                                      '%4x' % random.randrange(2 ** 32))

            status = write_file(model_dir, filename, data, dry_run)
            written_files[filename] = {'data': data, 'status': status}

    # Remove any existing files in the output directory that are obsolete
    removed = remove_obsolete_files(model_dir, written_files.keys(), dry_run)
    for filename in removed:
        written_files[filename] = {'data': None, 'status': DELETED}

    return written_files


def is_split_into_equal_number_of_files(model, section_name):

    # Count the entries in the fileSectionMap that contain only one
    # instance of the given section

    file_section_map = model['fileInfo']['fileSectionMap']
    for sections in file_section_map.values():
        for section in sections:
            if isinstance(section, dict) and section_name in section:
                id_list = section[section_name]
                if len(id_list) != 1:
                    return

    return True


def get_section_key_field(model, section_name):

    # Find a file that contains the given section and get its key field
    file_section_map = model['fileInfo']['fileSectionMap']
    for filename, sections in file_section_map.iteritems():
        for section in sections:
            try:
                if section_name in section:
                    return section['keyField']
            except (TypeError, KeyError, AttributeError):
                pass


def write_file(model_dir, filename, new_content, dry_run):

    filepath = os.path.join(model_dir, filename)

    parent_dir = os.path.dirname(filepath)
    if not os.access(parent_dir, os.R_OK):
        if not dry_run:
            os.makedirs(parent_dir)

    old_content = {}
    existed = False
    try:
        if os.access(filepath, os.R_OK):
            existed = True
            with open(filepath) as f:
                old_content = yaml.safe_load(f)
    except yaml.YAMLError:
        LOG.exception("Invalid yaml file %s", filepath)
    except IOError as e:
        LOG.error(e)

    # Avoid writing the file if the contents have not changes.  This preserves
    # any comments that may exist in the old file
    if new_content == old_content:
        return IGNORED
    else:
        LOG.info("Writing file %s", filename)
        if not dry_run:
            with open(filepath, "w") as f:
                yaml.safe_dump(new_content, f,
                               indent=2,
                               default_flow_style=False,
                               canonical=False)

    # Return an indication of whether a file was written (vs ignored)
    status = CHANGED if existed else ADDED
    return status


def remove_obsolete_files(model_dir, keepers, dry_run):

    # Report which files were deleted
    removed = []

    # Remove any yml files that are no longer relevant, i.e. not in keepers
    for root, dirs, files in os.walk(model_dir):
        for file in files:
            fullname = os.path.join(root, file)
            relname = os.path.relpath(fullname, model_dir)
            if file.endswith('.yml'):
                if relname not in keepers:
                    LOG.info("Deleting obsolete file %s", fullname)
                    if not dry_run:
                        os.unlink(fullname)
                    removed.append(relname)

    return removed
