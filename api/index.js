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

var express = require('express');
var bodyParser = require('body-parser');
var _ = require('lodash');

var templatesApi = require('./templates');
var playsApi = require('./plays');
var playbooksApi = require('./playbooks');
var serversApi = require('./servers');
var controlPlanesApi = require('./control-plane');
var configProcessorApi = require('./config-processor');
var configApi = require('./config');
var cpOutputApi = require('./cp-output');
var modelApi = require('./model');
var osInstallApi = require('./osinstall');
var resourcesApi = require('./resources');
var appConfigApi = require('./app-config');
var webSocketServer = require('../lib/websocket-server');
var processManager = require('../lib/process-manager');
var CurrentInputModel = require('../lib/current-input-model');
var cache = require('../lib/template-cache');
var logger = require('../lib/logger');

function init(parentApp, config, server) {

    logger.setConfig(config.get('logger'));

    process.on('uncaughtException', function(err) {

        var reportMe = ' Please report this issue to the developers by filing a ticket' +
            ' with the full log to the BRUI project.';
        try {
            logger.error('The following uncaught exception occurred: ' + JSON.stringify(err) + '.' +
                reportMe, err);
        } catch (error) {
            console.log('Failed to log uncaught exception: ' + err + ' due to: ' +
                error + '.' + reportMe);
        }
    });

    webSocketServer.start(server);
    processManager.init(config, webSocketServer);

    var apiApp = express();

    apiApp.disable('etag');

    // Disable caching of API responses
    apiApp.use(function(req, res, next) {
        res.set({
            'Cache-control': 'no-cache',
            'Pragma': 'no-cache',
            'Expires': 0
        });
        next();
    });

    var apiRouter = express.Router();
    apiRouter.use(bodyParser.json());

    // Because config uses raw text, we need a separate router
    var configRouter = express.Router();
    configRouter.use(bodyParser.text());

    // Heartbeat
    apiRouter.get('/heartbeat', function(request, response) {
        response.status(200).send(Date.now().toString());
    });

    // Version
    apiRouter.get('/version', function(request, response) {
        response.status(200).send(config.get('version') || 'Unknown version');
    });

    // Log requests
    apiApp.use(function(req, res, next) {

        // skip for heartbeat
        var heartbeatEndpoint = '/heartbeat';
        if (req.path === heartbeatEndpoint) {
            return next();
        }
        try {
            logger.info('Received request: ' + req.ip + ' ' + req.method + ' ' + req.path);
        } catch (error) {
            logger.warn('Failed to log request.', error);
        }

        // add hook to log response status code
        res.on('finish', function() {
            var size = res.get('Content-Encoding') === 'gzip' ? '[gzip compressed]' : res.get('Content-Length');
            try {
                logger.info('Sending response: ' + req.ip + ' ' + req.method + ' ' +
                    req.path + ' ' + res.statusCode + ' ' + size);
            } catch (error) {
                logger.warn('Failed to log request.', error);
            }
        });
        next();
    });

    appConfigApi.init(apiRouter, config);
    osInstallApi.init(apiRouter, config);

    logger.info('Template cache Initialising...');
    var cacheInitialised = cache.init(config);

    return cacheInitialised.then(function() {
        logger.info('Template cache initialised.');
    }, function() {
        logger.warn('Template cache failed to initialise. But we\'ll keep trying...');
    }).finally(function() {
        /** initialise Current Input Model **/
        CurrentInputModel.init(config, webSocketServer);
        templatesApi.init(apiRouter, config);
        playsApi.init(apiRouter);
        playbooksApi.init(apiRouter, config);
        configApi.init(configRouter, config);
        cpOutputApi.init(apiRouter, config);
        configProcessorApi.init(apiRouter, config);
        serversApi.init(apiRouter, config);
        controlPlanesApi.init(apiRouter);
        modelApi.init(apiRouter);
        resourcesApi.init(apiRouter);

        logger.info('Mounting ardana-service to: ' + config.get('apiEndpoint'));
        apiApp.use(apiRouter);
        apiApp.use(configRouter);
        parentApp.use(config.get('apiEndpoint'), apiApp);
    });

}
