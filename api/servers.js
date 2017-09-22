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
exports.getApiPath = function() {
    return SERVERS_PATH;
};

var Q = require('q');
var _ = require('lodash');

var constants = require('../lib/constants');
var utils = require('../lib/utils');
var ardanaProcess = require('../lib/ardana-process');
var logger = require('../lib/logger');

var currentInputModel = require('../lib/current-input-model');

var SERVERS_PATH = '/servers';

var _concurrentPromise = Q.resolve();

var concurrentServersReqError = {
    isUserError: 'Cannot run certain concurrent requests to server endpoint',
    code: constants.ERROR_CODES.SERVERS_CONCURRENT.code
};

function concurrentPromise() {
    // Helper method for requests that need to wait on previous requests to complete. May also consider returning
    // failed promise if previous request fails (we're in an unknown state).
    return _concurrentPromise.isPending() ? _concurrentPromise : Q.resolve();
}

function init(router, config) {

    // GET Servers
    router.get(SERVERS_PATH, function(request, response) {

        try {
            response.json({
                servers: currentInputModel.getServers()
            });
        } catch (err) {
            utils.sendErrorResponse(response, err, 'Failed to get servers');
        }
    });

    // Add a new server
    router.post(SERVERS_PATH, function(request, response) {
        currentInputModel.validateServer(request.body, true)
            .then(_.partial(currentInputModel.addServer, request.body))
            .then(function() {
                response.send();
            }).catch(function(err) {
                utils.sendErrorResponse(response, err, 'Failed to add new server');
        });
    });

    // Add a new server to model and apply changes (stage/commit -> ready -> deploy).
    // N.B. the http response is sent once deploy has started
    router.post(SERVERS_PATH + '/process', function(request, response) {

        if (_concurrentPromise.isPending()) {
            utils.sendErrorResponse(response, concurrentServersReqError);
            return;
        }

        _concurrentPromise = currentInputModel.getModel()
            .then(function(inputModel) {

                var server = {server: request.body.server};
                return currentInputModel.validateServer(server, true)
                    .then(_.partial(currentInputModel.addServer, server))
                    .then(function() {
                        // Deploy process handles response and logging for success/failure, so add a catch to log root
                        // caller and don't throw to avoid core catch
                        return ardanaProcess.deployProcess(request, response, config,
                            ardanaProcess.processSteps.monascaCheck, {
                                modelBeforeChange: inputModel
                            })
                            .catch(function() {
                                logger.error('Failed to deploy new server');
                            });
                    }).catch(function(err) {
                        utils.sendErrorResponse(response, err, 'Failed to add new server');
                    });
            }).catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to get updated model before delete');
            });
    });

// Update a server
    router.put(SERVERS_PATH + '/:id', function(request, response) {
        var serverId = request.params.id;
        currentInputModel.validateServer(request.body, false)
            .then(_.partial(currentInputModel.updateServer, serverId, request.body))
            .then(function() {
                response.send();
            }).catch(function(err) {
                utils.sendErrorResponse(response, err, 'Failed to update new server');
        });
    });

//// Get server info
//router.get(serversApiPrefix + '/:id', function(request, response) {
//
//    response.json({
//        status: true,
//        server: currentInputModel.getServer(request.params.id)
//    });
//});

// Delete server from model
    router.delete(SERVERS_PATH + '/:id', function(request, response) {

        currentInputModel.getModel()
            .then(_.partial(currentInputModel.deleteServer, request.params.id))
            .then(function() {
                response.send();
            })
            .catch(function(err) {
                utils.sendErrorResponse(response, err, 'Failed to delete server');
            });
    });


// Delete server from model and apply changes (stage/commit -> ready -> deploy)
    router.delete(SERVERS_PATH + '/:id' + '/process', function(request, response) {
        if (_concurrentPromise.isPending()) {
            utils.sendErrorResponse(response, concurrentServersReqError);
            return;
        }

        var modelBeforeChange;
        Q.when()
            .then(currentInputModel.getModel)
            .then(function(model) {
                // De-couple model from one that's about to change
                modelBeforeChange = JSON.parse(JSON.stringify(model));
                return model;
            })
            .then(_.partial(currentInputModel.deleteServer, request.params.id))
            // Deploy process handles response and logging for success/failure, so add a catch to log root
            // caller and don't throw to avoid core catch
            .then(function() {
                ardanaProcess.deployProcess(request, response, config, ardanaProcess.processSteps.ready, {
                        modelBeforeChange: modelBeforeChange
                    })
                    .then(function(data) {
                        response.send(data);
                    })
                    .catch(function() {
                        logger.error('Failed to delete new server');
                    });
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to delete server');
            });

    });

}
