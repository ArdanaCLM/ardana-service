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

var _ = require('lodash');
var fs = require('fs');
var Q = require('q');
var yaml = require('js-yaml');

var utils = require('../lib/utils');
var treeUtils = require('../lib/tree-utils');
var currentInputModel = require('../lib/current-input-model');

var CP_OUTPUT_PATH = require('./model').getApiPath() + '/cp_output';
var cpOutputDir;
var readyCpOutputDir;

function init(router, config) {

    cpOutputDir = config.get('paths:cpOutputDir');
    readyCpOutputDir = config.get('paths:readyCpOutputDir');

    router.get(CP_OUTPUT_PATH + '*', function(request, response) {

        var ready;
        try {
            ready = utils.parseBoolParam(request.query, 'ready');
        } catch (error) {
            return utils.sendErrorResponse(response, error);
        }

        var dir = ready ? readyCpOutputDir : cpOutputDir;
        currentInputModel.getCPOutputEntity(request.params[0], dir)
            .then(function(entity) {
                if (entity.unparseable) {
                    response.set('Last-Modified', entity.mtime);
                    response.set('Content-Type', 'text/plain');
                    return response.send(entity.bytes);
                }

                if (entity.isNotLeaf) {
                    return response.json(entity.subTree);
                }

                return response.json(entity.parsedEntity);
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error);
            });
    });

    return Q.resolve();
}

exports.init = init;
exports.getApiPath = function() {
    return CP_OUTPUT_PATH;
};
