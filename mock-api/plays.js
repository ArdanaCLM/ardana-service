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
var utils = require('../lib/utils');
var logger = require('../lib/logger');
var processManager = require('../lib/process-manager');
var currentInputModel = require('../lib/current-input-model');

var PLAYBOOKS_PATH = '/playbooks';
var PLAYS_PATH = '/plays';

// TODO: This is just a start - more work needed to build this out
// look to move the code embedded in the lib here, to separate out
// mock/test code

function init(config, mockApiRouter, mockApiData) {

    logger.info('Attaching mock handler for play/playbooks endpoints');

    var mockPlaybooks = {
        config_processor_run: config_processor_run,
        ready_deployment: ready_deployment,
        site: site
    };

    function handleAsyncSpawn(spawnPromise, response) {
        if (response) {
            spawnPromise.then(function(meta) {
                // Once the process has spawned, send the http response containing the pRef
                response.status(201).json(meta);
            }, function(error) {
                utils.sendErrorResponse(response, error, 'Failed to spawn ansible-playbook process');
            });
        }

        // Completion handling
        return spawnPromise.complete.then(function(meta) {
            logger.debug('Process ' + meta.pRef + ' completed successfully');
            return meta;
        }, function(meta) {
            var msg = 'Process ' + meta.pRef + ' exited with non zero code';
            logger.error(msg);
            throw meta;
        });
    }

    mockApiRouter.post(PLAYBOOKS_PATH + '/:name', function(request, response, next) {
        var playbook = request.params.name;

        // We can dispatch any playbook to our mock methods in this class if configured to do so
        // TODO: Selectively decide which mock mode to use

        // Mocking of plays must be configured on
        if (mockApiData.config.mockPlays) {
            // Config must enable the mocking of the play
            if (_.contains(mockApiData.config.mockPlays, playbook)) {
                // Mocking of this playbook is enabled
                var mockFn = mockPlaybooks[playbook];
                if (mockFn) {
                    return mockFn.apply(this, [request, response]);
                }
            }
        }

        if (mockApiData.config.failOtherPlays) {
            response.status(500).send('Mock API: Failing API playbook request: ' + playbook);
        } else {
            return next();
        }
    });

    // Get the list of plays
    mockApiRouter.get(PLAYS_PATH, function(request, response, next) {
        if (mockApiData.config.playsList) {
            return response.send(mockApiData.config.playsList);
        } else {
            if (mockApiData.config.failPlaysList) {
                response.status(500).send('Mock API: Failing API plays list request');
            } else if (mockApiData.config.passPlaysList) {
                // Return an empty list
                response.status(200).send([]);
            } else {
                return next();
            }
        }
    });

    // Mock helpers to run the Mock playbooks

    function config_processor_run(request, response) {
        var opts = {
            encryption_key: request.body.encrypt || '""',
            prev_encryption_key: request.body.rekey || '""',
            remove_deleted_servers: request.body.removeDeletedServers,
            free_unused_addresses: request.body.freeUnusedAddresses,
            userId: request.headers.clientid
        };
        var args = [];
        var spawnPromise = spawnAnsiblePlay('openstack/ardana/ansible/', 'hosts/localhost',
            'config-processor-run.yml', args, false, opts.userId);
        return handleAsyncSpawn(spawnPromise, response);

    }

    function ready_deployment(request, response) {
        var spawnPromise = spawnAnsiblePlay('openstack/ardana/ansible/', 'hosts/localhost',
            'ready-deployment.yml', null, true, request.headers.clientid);
        spawnPromise.then(function() {
            spawnPromise.complete.then(function() {
                logger.debug('Ready Deploy completed successfully');
                currentInputModel.notifyClients();
            });
        });
        return handleAsyncSpawn(spawnPromise, response);
    }

    function site(request, response) {
        var opts = {
            limit: request.body.limit,
            clientId: request.headers.clientid,
            keepDayZero: request.body.keepDayZero,
            destroyDayZeroOnSuccess: request.body.destroyDayZeroOnSuccess
        };
        var args = [];
        var promise = spawnAnsiblePlay('scratch/ansible/next/ardana/ansible', 'hosts/verb_hosts',
            'site.yml', args, true, opts.clientId);
        return handleAsyncSpawn(promise, response);
    }

    function spawnAnsiblePlay(cwd, inventoryFile, playbook, args, preventConcurrentRuns, userId) {
        console.log('TEST SPAWN RUNNING');
        var ansibleArgs = ['-i', inventoryFile, playbook];

        //if (config.isMocked() && _.indexOf(config.get('testing:mockPlaybooks'), playbook) >= 0) {

        var command = 'node';

        // TODO: Don't ../.. : Set a clear expectation whgere the script path is relative to
        // TODO: We can probably fix this script path - not sure we need the flexibility to set this?
        // TODO: Maybe have a default value?
        // Put the mock script name at the start of the args, so it is run

        var mockScript = 'misc/ansible-mock/ansible.js';
        if (config.get('testing:mockAnsibleScript')) {
            mockScript = config.get('testing:mockAnsibleScript');
        }
        // Script is relative to the ardana-service folder
        var mockScriptPath = path.join(__dirname, '..', mockScript);
        ansibleArgs.unshift(mockScriptPath);
        cwd = '';
        if (args) {
            ansibleArgs.push.apply(ansibleArgs, args);
        }

        var env = {
            ANSIBLE_FORCE_COLOR: true,
            PYTHONUNBUFFERED: 1,
            HOME: config.get('HOME')
        };

        if (mockApiData.config.logReplaySpeed) {
            console.log('SETTING LOG REPLAY SPEED TO: ' + mockApiData.config.logReplaySpeed);
            env.MOCK_REPLAY_SPEED = mockApiData.config.logReplaySpeed;
        }

        return processManager.spawnProcess(cwd, command, ansibleArgs, {
            env: env,
            preventConcurrentRuns: preventConcurrentRuns,
            userId: userId
        });
    }
}

function reset() {}

module.exports.init = init;
module.exports.reset = reset;
