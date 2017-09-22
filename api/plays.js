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

var processManager = require('../lib/process-manager');
var fs = require('fs');
var logger = require('../lib/logger');
var utils = require('../lib/utils');

var PLAYS_PATH = '/plays';
var ANSI_COLOUR_MATCHER = new RegExp('(?:\x1B\\[[0-9;]*m[\n]*)+', 'g');

function init(router) {

    // List all Ansible plays (live and finished)
    router.get(PLAYS_PATH, function(request, response) {
        processManager.getPlays(request.query).then(function(allPlays) {
            response.json(allPlays);
        }, function(error) {
            utils.sendErrorResponse(response, error, 'Failed to list processes!');
        });
    });

    // Get play meta data by reference. This will NOT include the log
    router.get(PLAYS_PATH + '/:pRef', function(request, response) {
        var pRef = request.params.pRef;

        processManager.getMeta(pRef, true).then(function(meta) {
            response.json(meta);
        }, function(error) {
            utils.sendErrorResponse(response, error, 'Failed to get log meta data!');
        });

    });

    // Get play log by reference, by default we return a JSON envelope with the log contents
    // If ?raw=true is specified we send the raw log output instead
    router.get(PLAYS_PATH + '/:pRef/log', function(request, response) {
        var pRef = request.params.pRef;

        var raw;
        try {
            raw = utils.parseBoolParam(request.query, 'raw');
        } catch (error) {
            return utils.sendErrorResponse(response, error);
        }
        if (raw) {
            processManager.getLogFilePath(pRef).then(function(path) {
                response.download(path);
            }).catch(function(error) {
                utils.sendErrorResponse(response, error);
            });
            return;
        }

        var maxSize;
        try {
            maxSize = utils.parseIntParam(request.query, 'maxSize');
        } catch (error) {
            return utils.sendErrorResponse(response, error);
        }

        processManager.getLog(pRef, maxSize).then(function(log) {
            if (utils.parseBoolParam(request.query, 'noColor')) {
                log = log.replace(ANSI_COLOUR_MATCHER, '');
            }
            response.json({
                pRef: pRef,
                log: log
            });
        }).catch(function(error) {
            utils.sendErrorResponse(response, error, 'Failed to get log by reference!');
        });

    });

    // Kill a play process by reference
    router.delete(PLAYS_PATH + '/:pRef', function(request, response) {
        var pRef = request.params.pRef;
        try {
            processManager.kill(pRef);
        } catch (error) {
            return utils.sendErrorResponse(response, error, 'Failed to kill process by reference!');
        }
        return response.json({
            pRef: pRef,
            message: 'process, PID: ' + pRef + ' killed'
        });
    });

}
