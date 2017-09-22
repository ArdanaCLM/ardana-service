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

var fs = require('fs');
var Q = require('q');

var utils = require('../lib/utils');
var treeUtils = require('../lib/tree-utils');

var readFileQ = Q.denodeify(fs.readFile);
var writeFileQ = Q.denodeify(fs.writeFile);

var CONFIG_PATH = require('./model').getApiPath() + '/config';
var configDir;

function init(router, config) {

    configDir = config.get('paths:configDir');

    // List and retrieve config entities
    router.get(CONFIG_PATH + '*', function(request, response) {

        // Always refresh all entities
        treeUtils.scanDirectory(configDir).then(function(allEntities) {
            allEntities = utils.sortKeys(allEntities);
            var subTree = treeUtils.getRelevantSubtree(request.params[0], allEntities);
            if (treeUtils.isLeaf(subTree)) { // A leaf! Return the file contents
                return readFileQ(subTree._path_, 'utf8').then(function(bytes) {
                    response.set('Last-Modified', subTree._mtime_.toUTCString());
                    response.set('Content-Type', 'text/plain');
                    response.send(bytes);
                });
            }
            return response.json(treeUtils.nullTerminateLeaves(subTree));
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Replace the contents of a config entity
    router.put(CONFIG_PATH + '*', function(request, response) {
        var bytes = request.body;

        if (!bytes) {
            return utils.sendErrorResponse(response, {
                isUserError: "You must provide the new content of the file as the request's body",
                statusCode: 400
            });
        }

        // Always refresh all entities
        treeUtils.scanDirectory(configDir).then(function(allEntities) {
            var subTree = treeUtils.getRelevantSubtree(request.params[0], allEntities);
            if (treeUtils.isLeaf(subTree)) { // A leaf! Write the new file contents
                return writeFileQ(subTree._path_, bytes, 'utf8').then(function() {
                    response.status(204).send();
                });
            }
            throw { // Cannot write to non-leaf node
                isUserError: 'Path not a leaf node in config tree: ' + request.params[0],
                statusCode: 400
            };
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    return Q.resolve();
}

exports.init = init;
exports.getApiPath = function() {
    return CONFIG_PATH;
};
