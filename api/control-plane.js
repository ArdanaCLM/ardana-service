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

exports.init = init;
/** Used for tests **/
exports.getApiPath = function() {
    return CONTROL_PLANES_PATH;
};

var _ = require('lodash');

var constants = require('../lib/constants');
var utils = require('../lib/utils');
var currentInputModel = require('../lib/current-input-model');

var CONTROL_PLANES_PATH = '/controlplanes';

function init(router) {

    // Get all control planes
    router.get(CONTROL_PLANES_PATH, function(request, response) {
            currentInputModel.getControlPlanes()
            .then(function(planes) {
                response.json({
                    'control-planes': planes
                });
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to get control planes!');
            });
    });

    // Get named control plane
    router.get(CONTROL_PLANES_PATH + '/:id', function(request, response) {
        var controlPlaneName = request.params.id;
        currentInputModel.getControlPlane(controlPlaneName)
            .then(function(plane) {
                response.json({
                    'control-plane': plane
                });
            }).catch(function(error) {
            utils.sendErrorResponse(response, error, 'Failed to get named control plane!');
        });
    });

    // Add a cluster to the named control plane
    router.post(CONTROL_PLANES_PATH + '/:id/clusters', function(request, response) {
        var controlPlaneName = request.params.id;
            currentInputModel.addCluster(controlPlaneName, request.body).then(function() {
                response.status(201).send();
            }).catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to add new cluster');
            });
    });
}
