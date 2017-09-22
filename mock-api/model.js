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

var path = require('path');
var _ = require('lodash');

var logger = require('../lib/logger');

var MODEL_PATH = '/model';
var TEMPLATES_PATH = '/templates';

// Model state
var savedModel;

function init(config, mockApiRouter, mockApiData) {

    logger.info('Attaching mock handler for model/templates endpoints');

    // If templates path is set then serve up canned templates form that folder
    if (mockApiData.config.templatePath) {
        mockApiRouter.get(TEMPLATES_PATH + '/:name?', function(request, response) {
            var file = (request.params.name || 'index') + '.json';
            var filePath = path.join(config.get('topLevelBaseDir'), mockApiData.config.templatePath, file);
            response.sendFile(filePath);
        });
    }

    // Prevent model writes
    mockApiRouter.post(MODEL_PATH, function(request, response) {
        // modelWriteFailures: 0 always passes, +N passes N times, -1 always fails
        var failCount = mockApiData.config.modelWriteFailures;
        if (!failCount) {
            failCount = 0;
            mockApiData.config.modelWriteFailures = failCount;
        }

        // +ve value means okay
        if (failCount >= 0) {
            savedModel = request.body;
            response.send('Mock API: Model stored in memory');
            if (failCount > 0) {
                mockApiData.config.modelWriteFailures--;
            }
        } else {
            response.status(500).send('Mock API: Simulating model write failure');
        }
    });

    // Model read
    mockApiRouter.get(MODEL_PATH, function(request, response) {
        var failCount = mockApiData.config.modelReadFailures;
        if (!failCount) {
            failCount = 0;
            mockApiData.config.modelReadFailures = failCount;
        }

        if (failCount >= 0) {
            if (mockApiData.config.modelFile) {
                var filePath = path.join(config.get('topLevelBaseDir'), mockApiData.config.modelFile);
                response.sendFile(filePath);
            } else {
                if (_.keys(savedModel).length === 0) {
                        response.status(404).send('Mock API: No existing model');
                } else {
                    response.send(savedModel);
                }
            }
            if (failCount > 0) {
                mockApiData.config.modelReadFailures--;
            }
        } else {
            response.status(404).send('Mock API: Pretending that there is no existing model');
        }
    });

    // Commit model changes
    mockApiRouter.post( MODEL_PATH + '/commit*', function(request, response) {
        // Store the commited model - we will return this if someone asks for the extended model
        savedModel = request.body;
        response.status(200).send('Mock API: Simulating successful commit of the input model');
    });

    // Get the expanded model - just return the last one saved (for now)
    mockApiRouter.get( MODEL_PATH + '/expanded', function(request, response) {
        //response.send(savedModel);
        console.log(mockApiData.config)
        response.send(mockApiData.config);
    });
}

function reset() {
    savedModel = {};
}


// Reset on load
reset();

module.exports.init = init;
module.exports.reset = reset;
