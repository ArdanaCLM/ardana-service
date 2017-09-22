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

// Note: this is the entry point for the standalone version of ardana-service

// Ensure the working directory is what we expect
process.chdir(__dirname);

var express = require('express');
var http = require('http');
var app = express();
var server = http.createServer(app);
var compression = require('compression');
var config = require('./config');
var api = require('./api');
var logger = require('./lib/logger');
var cors = require('cors');
var keystone = require('./lib/keystone');
var processManager = require('./lib/process-manager');

app.use(compression());
app.use(cors());

// When used as an API Service, Keystone authentication is enabled
app.use(keystone(config));

// Add property to identify that HUX-SVC is running in a stand-alone fashion
config.set('isStandalone', true);

var port = config.get('port');
var bindAddress = config.get('bindAddress');
var apiInitPromise = api.init(app, config, server);

apiInitPromise.then(function() {
    logger.info('REST API initialised');
    server.listen(port, bindAddress, function() {
        logger.info('\x1b[32mHTTP Server starts listening on %s:%d ...\x1b[0m', bindAddress, port);
    });
}).catch(function(err) {
    logger.error('Failed to initialise REST API!', err);
    process.exit(1);
});

// process exit hook
function shutdownHook() {
    logger.info('Ardana REST Service is preparing to shutdown...');
    processManager.preventSpawn();
    logger.debug('Prevented spawning of any new processes...');

    function checkRunningProcesses() {
        if (!processManager.areProcessesRunning()) {
            logger.info('No more processes are running, shutting down!');
            return process.exit(0);
        }
        setTimeout(checkRunningProcesses, 50);
    }

    checkRunningProcesses();
}

process.on('SIGINT', function() {
    // Ctr-C
    shutdownHook();
});

process.on('SIGTERM', function() {
    // Systemd stop
    shutdownHook();
});

module.exports.express = app;
