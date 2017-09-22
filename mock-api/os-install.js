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

var logger = require('../lib/logger');

var OS_INSTALL_PATH = '/osinstall';

// Current OS Install State
var osInstall, osInstallSequence;

function init(config, mockApiRouter) {

    logger.info('Attaching mock handler for osinstall endpoint');

    // Start an OS Install
    mockApiRouter.post(OS_INSTALL_PATH, function(request, response) {
        osInstallSequence = [];
        osInstall = {
            finished: false,
            hasError: false,
            servers: {}
        };

        var countDown = 1;
        _.each(request.body.servers, function(svr) {
            osInstall.servers[svr.id] = 'installing';
            osInstallSequence.push({
                id: svr.id,
                countdown: countDown
            });
            countDown++;
        });
        response.status(200).send('Mock API: Pretending OS Install started OK');
    });

    // OS Install status check
    mockApiRouter.get(OS_INSTALL_PATH, function(request, response) {
        if (!osInstall.finished) {
            var complete = 0;
            var errors = 0;
            // Everytime we do a get, we'll pretend to action the install along
            _.each(osInstallSequence, function(svr) {
                if (svr.countdown === 0) {
                    complete++;
                    if(svr.id.indexOf('__fail_') === 0)  {
                        osInstall.servers[svr.id] = 'error';
                        errors++;
                    } else {
                        osInstall.servers[svr.id] = 'complete';
                    }
                } else {
                    svr.countdown--;
                }
            });
            osInstall.finished = (complete === osInstallSequence.length);
            osInstall.hasError = (errors > 0);
        }
        response.send(osInstall);
    });
}

function reset() {
    osInstall = {};
    osInstallSequence = [];
}

// Reset on load
reset();

module.exports.init = init;
module.exports.reset = reset;
