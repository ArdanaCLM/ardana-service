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
    return RESOURCES_PATH;
};

var constants = require('../lib/constants');
var utils = require('../lib/utils');
var currentInputModel = require('../lib/current-input-model');
var RESOURCES_PATH = '/resources';

function init(router) {

    function fetchServerRoles() {
        // At the moment the available servers can only support one type of role...
        // so only return this one role
        return currentInputModel.getServerRoles();
    }

    // Retrieve available resources (spare servers and server-roles)
    router.get(RESOURCES_PATH, function(request, response) {
            currentInputModel.getModel().then(function(model) {
                var servers = currentInputModel.getAvailableServers(model);
                response.json({
                    succeeded: true,
                    servers: servers,
                    roles: {
                        server: fetchServerRoles()
                    }
                });
            }).catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to fetch resources');
            });

        }
    );

}
