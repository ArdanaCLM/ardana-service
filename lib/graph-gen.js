/**
 * (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
 * (c) Copyright 2017 SUSE LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License. You may obtain
 * a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations
 * under the License.
 */
'use strict';

exports.generate = generate;

//////////

var constants = require('./constants');
var path = require('path');
var fs = require('fs');
var yaml = require('js-yaml');
var _ = require('lodash');

var INPUT_MODEL = constants.INPUT_MODEL;

var COLORS = {
    'server': '#59bbe4',
    'server_roles': '#80c595',
    'disk_models': '#eaa61f',
    'interface_models': '#eda6a6',
    'error': '#ff0000'
};

var STYLES = {
    'server': {
        color: '#59bbe4',
        shape: 'icon',
        icon: {
          code: '\uf233',
          color: '#59bbe4'
        }
    },
    'server_roles': {
        color: '#80c595',
        shape: 'icon',
        icon: {
          code: '\uf007',
          color: '#80c595'
        }
    },
    'disk_models': {
        color: '#eaa61f',
        shape: 'icon',
        icon: {
          code: '\uf1c0',
          size: 35,
          color: '#eaa61f'
        }
    },
    'interface_models': {
        color: '#eda6a6',
        shape: 'icon',
        icon: {
          code: '\uf1e0',
          color: '#eda6a6'
        }
    },
    'error': {
        color: '#ff0000'
    },
    'baremetal_servers': {
        color: '#d3d3d3',
        size: 12,
        shape: 'icon',
        icon: {
          code: '\uf233',
          color: '#d3d3d3',
          size: 25
        }
    },
    'control_planes': {
        color: '#40a860',
        size: 30,
        shape: 'icon',
        icon: {
          code: '\uf0c2',
          size: 60,
          color: '#40a860'
        }
    },
    'control_planes_clusters': {
        shape: 'icon',
        icon: {
          code: '\uf1b3',
          size: 45
        }
    },
    'control_planes_resource_nodes': {
        shape: 'icon',
        icon: {
          code: '\uf1b3',
          size: 45
        }
    },
    'disk_models_volume_groups': {
        color: '#c1d0d2',
        size: 15,
        shape: 'icon',
        icon: {
          code: '\uf07b',
          size: 25,
          color: '#c1d0d2'
        }
    },
    'networks': {
        color: '#e9c8f9',
        shape: 'icon',
        size: 20,
        icon: {
          code: '\uf1eb',
          size: 30,
          color: '#e9c8f9'
        }
    },
    'network_groups': {
        color: '#d4b4ec',
        shape: 'icon',
        icon: {
          code: '\uf1ad',
          size: 30,
          color: '#d4b4ec'
        }
    },
    'interface_models_network_interfaces': {
        color: '#d85959',
        shape: 'icon',
        icon: {
          code: '\uf0ec',
          size: 30,
          color: '#d85959'
        }
    }
};

function generate(template) {

    var graph = {
        nodeIndex: 0,
        groupIndex: 0,
        nodeMap: {},
        nodeTypeMap: {},
        nodeTypeList: {},
        nodes: [],
        edges: [],
        errors: []
    };

    // Add nodes for all of the servers
    addNodes(graph, template[INPUT_MODEL].servers, 'server', ['id', 'ip-addr']);
    addNodes(graph, template[INPUT_MODEL]['server-roles'], 'server_roles', 'name');

    addNodes(graph, template[INPUT_MODEL]['disk-models'], 'disk_models', 'name');
    addNodes(graph, template[INPUT_MODEL]['interface-models'], 'interface_models', 'name');

    //addNodes(graph, template[INPUT_MODEL]['baremetal_servers'], 'baremetal_servers', 'node_name');

    addNodes(graph, template[INPUT_MODEL]['control-planes'], 'control_planes', 'name');

    addChildNodes(graph, template[INPUT_MODEL], 'control-planes/clusters', 'id', 'name', 'has cluster');
    addChildNodes(graph, template[INPUT_MODEL], 'control-planes/resource-nodes', 'name', 'name', 'has resources');

    addChildNodes(graph, template[INPUT_MODEL], 'disk-models/volume-groups', 'name', 'name', 'has volume group');

    addChildNodes(graph, template[INPUT_MODEL], 'interface-models/network-interfaces', 'name', 'name', 'has net intf');

    addNodes(graph, template[INPUT_MODEL]['network-groups'], 'network_groups', 'name');
    addNodes(graph, template[INPUT_MODEL]['networks'], 'networks', 'name');

    addRelationship(graph, 'server', 'server_roles', 'role', 'has server role');

    addRelationship(graph, 'server_roles', 'disk_models', 'disk-model', 'has disk model');
    addRelationship(graph, 'server_roles', 'interface_models', 'interface-model', 'has interface model');

    // TODO: Baremetal server - how do we know which server ralates to which baremetal serveR?
    // Positional index?
    // Currently we look at the id or ip-addr>pxe_ip_addr to link them up
    //addRelationship(graph, 'server', 'baremetal_servers', 'id', 'has baremetal', {'ip-addr': 'pxe_ip_addr'});

    addRelationship(graph, 'control_planes_clusters', 'server_roles', 'server-role', 'in cluster');
    addRelationship(graph, 'control_planes_resource_nodes', 'server_roles', 'server-role', 'is compute resource');

    // Relate networks groups to network interfaces
    addRelationship(graph, 'interface_models_network_interfaces', 'network_groups', 'network-groups', 'in net group');

    addRelationship(graph, 'networks', 'network_groups', 'network-group', 'in net grp');

    addGroup(graph, 'server_roles', 'server');

    addGroup(graph, 'control_planes');

    return {
        nodes: graph.nodes,
        edges: graph.edges,
        errors: graph.errors
    };
}

function getTypeName(key) {
    return key.replace('-', '_').replace('/', '_');
}

function addGroup(graph, nodeType, refType) {

  _.each(graph.nodeTypeMap[nodeType], function(node) {
    var id = node.id;
    var grpId = graph.groupIndex;
    graph.groupIndex++;
    node.group = grpId;
    _.each(graph.edges, function(edge) {
      if (edge.to === id) {
        var edgeNode = graph.nodes[edge.from];
        if (edgeNode && (!refType || edgeNode.nodeType === refType)) {
          edgeNode.group = grpId;
        }
      }
    });
  });
}

function getNodeId(obj, idFields) {
  if (!Array.isArray(idFields)) {
    return obj[idFields];
  } else {
    for (var i = 0; i < idFields.length; i++) {
      var field = idFields[i];
      if (obj[field]) {
        return obj[field];
      }
    }
  }
  return null;
}

function addNodes(graph, objects, typeName, idField, isError) {

    var added = [];

    _.each(objects, function(obj) {

        var name = typeName + '_' + obj[idField];
        var index = graph.nodeIndex;
        graph.nodeIndex++;

        var node = {
            id: index,
            name: getNodeId(obj, idField),
            nodeType: typeName,
            label: getNodeId(obj, idField),
            metadata: obj
        };

        if (COLORS[typeName]) {
            node.color = COLORS[typeName];
        }

        if (STYLES[typeName]) {
            node = _.defaults(node, STYLES[typeName]);
        }

        if (isError) {
            var colors = {};
            colors.background = node.color;
            colors.border = 'red';
            node.color = colors;
            node.shape = 'triangle';
            node.borderWidth = 4;
        }


        graph.nodeMap[name] = node;
        graph.nodes.push(node);

        if (!graph.nodeTypeMap[typeName]) {
          graph.nodeTypeMap[typeName] = {};
          graph.nodeTypeList[typeName] = [];
        }

        graph.nodeTypeMap[typeName][node.label] = node;

        // Keep a list - the id does not have to be unique if not referencing in, in some cases
        graph.nodeTypeList[typeName].push(node);

        added.push(node);
    });

    return added;
}

function addChildNodes(graph, object, childPath, idField, parentIdField, relationship) {

    var path = childPath.split('/');
    if (path.length !== 2) {
        console.log('ERROR: Only parent/child paths supported');
        return;
    }

    var parentField = path[0];
    var childField = path[1];
    var typeName = getTypeName(parentField) + '_' + getTypeName(childField);
    var p = object[parentField];
    _.each(p, function(pItem) {
            var childNodes = addNodes(graph, pItem[childField], typeName, idField);
            var parentGraphNode = graph.nodeTypeMap[getTypeName(parentField)][pItem[parentIdField]];
            _.each(childNodes, function(childNode) {
                var linkObj = {
                    'from': parentGraphNode.id,
                    'to': childNode.id
                };
            if (relationship) {
                linkObj.label = relationship.replace(' ', '\n').replace(' ', '\n');
            }
            graph.edges.push(linkObj);
        });
    });

}

function lookupNode(graph, source, destType, otherLinks) {
  if (!otherLinks) return null;
  var found = null;
  _.find(Object.keys(otherLinks), function(sourceLink) {
    var destLink = otherLinks[sourceLink];
    var sourceValue = source.metadata[sourceLink];
    _.find(graph.nodeTypeMap[destType], function(destNode) {
      var destValue = destNode.metadata[destLink];
      if (destValue && sourceValue && destValue === sourceValue) {
        found = destNode;
        return true;
      }
    });
  });
  return found;
}

function addRelationship(graph, sourceType, destType, linkField, relationship, otherLinks) {

    //console.log(sourceType + ', ' + linkField);

        _.each(graph.nodeTypeList[sourceType], function(obj) {
          //console.log(obj);

            var linkObj = obj.metadata[linkField];

            if (!Array.isArray(linkObj)) {
                linkObj = [linkObj];
            }

            _.each(linkObj, function(linkObjRef) {

                var link = destType + '_' + linkObjRef;

              //  console.log(link);

                var lookup = graph.nodeMap[link];
                if (!lookup) {

                  // Could not find the node from the linkField - what about the otherLinks?
                  lookup = lookupNode(graph, obj, destType, otherLinks);
                  if (!lookup) {

                    // ERROR
                    console.log('Can not find link: ' + link);
                     graph.errors.push('Missing node for link: ' + link);

                    var errorObj = {};
                    errorObj['error'] = obj.metadata[linkField];

                    lookup = addNodes(graph, [errorObj], destType, 'error', true);
                    lookup = lookup[0];
                  }
                }

                var edgeObj = {
                    'from': obj.id,
                    'to': lookup.id
                };

                if (relationship) {
                    edgeObj.relationship = relationship;
                    edgeObj.label = relationship.replace(' ', '\n').replace(' ', '\n');
                    edgeObj.arrows = 'to';
                } else {
                    // Child node relationship
                    //linkObj.arrows = 'to';
                }

                graph.edges.push(edgeObj);
            });
        });
}
