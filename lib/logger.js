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

var winston = require('winston');
var _ = require('lodash');

var defaultConfig = {
    level: 'debug',
    handleExceptions: true,
    json: false,
    colorize: true,
    timestamp: true
};

var ansiColourCodeRegex = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;

var logger = new winston.Logger({
    transports: [
        new winston.transports.Console(defaultConfig)
    ]
});

var setConfig = function(loggerConfig) {

    loggerConfig = loggerConfig || {};

    var transports = [];

    if (_.has(loggerConfig, 'console')) {
        transports.push(new winston.transports.Console(_.assign({}, defaultConfig, loggerConfig.console)));
    }

    function sanitiseMessage(msg) {
        /** strip colours */
        return msg.replace(ansiColourCodeRegex, '');
    }

    if (_.has(loggerConfig, 'file')) {

        var fileTransport = new winston.transports.File(_.assign({}, defaultConfig, loggerConfig.file));
       /** override File transports 'log' method to remove colour codes in messages **/
        fileTransport._log = fileTransport.log;
        fileTransport.log = function(level, msg, meta, callback) {
            var cleanMessage = sanitiseMessage(msg);
            fileTransport._log(level, cleanMessage, meta, callback);
        };

        transports.push(fileTransport);
    }


    logger.configure({
        transports: transports
    });
};

module.exports = logger;
module.exports.setConfig = setConfig;
