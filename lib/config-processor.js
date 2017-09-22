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
var temp = require('temp').track();
var path = require('path');
var Q = require('q');
var yaml = require('js-yaml');

var logger = require('./logger');
var processManager = require('./process-manager');
var constants = require('./constants');
var utils = require('./utils');
var currentInputModel = require('./current-input-model');
var statQ = Q.denodeify(fs.stat);

var INPUT_MODEL = constants.INPUT_MODEL;
var CP_VERSION = constants.CP_VERSION;

function ConfigProcessor(config) {
    this.config = config;
    _.bindAll.apply(_, [this].concat(_.functions(ConfigProcessor.prototype)));
}

/**
 * get current configuration
 * Executes Config Processor in a temporary directory and returns the CloudModel.json.
 */
function get() {

    var tempPath = temp.mkdirSync();

    var command = path.join(this.config.get('configProcessor:rootPath'), 'venv', 'bin', 'python');
    var args = [];
    args.push(path.join(this.config.get('configProcessor:rootPath'), 'venv', 'share',
        'ardana-config-processor', 'Driver', 'ardana-cp'));
    args.push('-l');
    args.push(tempPath + '/log');
    args.push('-c');
    args.push(path.join(this.config.get('paths:cloudDir'), 'cloudConfig.yml'));
    args.push('-s');
    args.push(this.config.get('paths:servicesPath'));
    args.push('-r');
    args.push(this.config.get('configProcessor:schemaPath'));

    logger.debug('Executing... ' + command + ' ' + args.join(' '));

    return processManager.spawnProcess(tempPath, command, args, {description: 'validate input model'})
        .complete.then(currentInputModel.getModel, function(meta) {
            logger.error('Config Processor failed!');
            throw meta;
        }).then(function(model) {
            var modelName = model[INPUT_MODEL].cloud.name;
            var filePath = path.join(tempPath, 'clouds', modelName, CP_VERSION, 'stage', 'info');
            return statQ(filePath);
        }).catch(function(error) {
            logger.error('Failed to validate input model.');
            throw error;
        });
}

ConfigProcessor.prototype.get = get;
module.exports = ConfigProcessor;
