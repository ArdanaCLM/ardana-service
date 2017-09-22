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

var constants = require('../lib/constants');
var _ = require('lodash');
var OSInstaller = require('../lib/os-installer');
var logger = require('../lib/logger');
var OS_INSTALL_PATH = '/osinstall';

function init(router, config) {

    // Start a new OS install
    router.post(OS_INSTALL_PATH, function(request, response) {
        OSInstaller.setup()
            .then(function() {
                response.status(201).send();
            }, function(error) {
                response.status(500).send(error);
                throw error;
            })
            .then(_.partial(OSInstaller.install, config, request.body))
            .catch(function(error) {
                logger.error('Exception occurred during osinstall!', error);
            });

    });

    // Retrieve the OS installation status
    router.get(OS_INSTALL_PATH, function(request, response) {
        response.status(200).send(OSInstaller.status());
    });
}
