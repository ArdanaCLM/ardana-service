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

var _ = require('lodash');
var express = require('express');
var bodyParser = require('body-parser');

// API will initialize the log level
var logger = require('../lib/logger');

// API Mocks
var mockModel = require('./model');
var mockOSInstall = require('./os-install');
var mockPlaybooks = require('./plays');


// Control endpoint for changing the mock API behaviour
var MOCK_API_CONTROL = '/mock-api';

function init(parentApp, config) {
    logger.setConfig(config.get('logger'));

    var mockApiApp = express();
    mockApiApp.use(bodyParser.json());
    mockApiApp.disable('etag');

    // Disable caching of Mock API responses
    mockApiApp.use(function(req, res, next) {
        res.set({
            'Cache-control': 'no-cache',
            'Pragma': 'no-cache',
            'Expires': 0
        });
        next();
    });


    var mockApiData = {};

    // Mock API Configuration
    var mockApiConfig = config.get('testing') || {};

    // Store the original configuration set when first run
    var originalTestConfig = _.cloneDeep(mockApiConfig);

    mockApiData.config = mockApiConfig;

    // Mock API Router
    var mockApiRouter = express.Router();

    // Log all requests made to the Mock API
    mockApiRouter.all('/*', function(request, response, next) {
        logger.info('Mock API: ' + request.method + ' ' + request.path);
        return next();
    });

    // Allow the Mock API config to be changed
    // You can not turn off mocked features but you can change config which
    // these use to change their behaviour
    mockApiRouter.post(MOCK_API_CONTROL, function(request, response) {
        var config = request.body;
        // Overwrite the properties in testConfig by those supplied
        _.assign(mockApiData.config, config);
        response.send(mockApiData.config);
    });

    // Get the current Mock API configuration
    mockApiRouter.get(MOCK_API_CONTROL, function(request, response) {
        response.send(mockApiData.config);
    });

    // Get the current Mock API configuration
    mockApiRouter.delete(MOCK_API_CONTROL, function(request, response) {
        // Restore the test config to values when first loaded
        mockApiData.config = _.cloneDeep(originalTestConfig);
        // Allow all the mocks to reset state
        mockModel.reset();
        mockOSInstall.reset();
        mockPlaybooks.reset();
        // Send back the current mock config
        response.send(mockApiData.config);
    });

    // Init the mocks
    if (config.get('testing:mockModel')) {
        mockModel.init(config, mockApiRouter, mockApiData);
    }
    if (config.get('testing:mockOSConfig')) {
        mockOSInstall.init(config, mockApiRouter, mockApiData);
    }
    if (config.get('testing:mockPlaybooks')) {
        mockPlaybooks.init(config, mockApiRouter, mockApiData);
    }
    // Prevent anything passing through that was not already handled
    if (mockApiData.config.allElseFails) {
        mockApiRouter.all('/*', function(request, response) {
            response.status(500).send('Mock API: Failing API request');
        });
    }

    // Only add the mock API routes if we are running in mock mode (isMocked)
    if (config.isMocked()) {
        logger.warn('Mounting ardana-service Mock API: ' + config.get('apiEndpoint'));
        mockApiApp.use(mockApiRouter);
        parentApp.use(config.get('apiEndpoint'), mockApiApp);
    }
}
