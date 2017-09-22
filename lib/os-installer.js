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

var constants = require('./constants');
var _ = require('lodash');
var Q = require('q');
var processManager = require('./process-manager');
var path = require('path');
var yaml = require('js-yaml');
var fs = require('fs');
var logger = require('./logger');
var childProcess = require('child_process');
var exec = childProcess.exec;

var states = {
    COMPLETE: 'complete',
    ERROR: 'error',
    INSTALLING: 'installing',
    PWR_ERROR: 'pwr_error',
    READY: 'ready',
    REMOVE: 'remove'
};

var servers = [];
var localIps = [];
var playbookDir = 'openstack/ardana/ansible/';

function setup() {
    return initLocalIps();
}

function install(config, osConfig) {

    var userPassword = osConfig.baremetal.user_password;
    var disablePwdAuth = osConfig.baremetal.disable_pwd_auth;
    delete osConfig.baremetal.user_password;
    delete osConfig.baremetal.cloud;

    if (!osConfig.product) {
        osConfig.product = {version: 2};
    }

    var failedNodes = [], newServers = {};
    if (osConfig.servers) {
        osConfig.servers.forEach(function(server) {
            var name = server.id;
            if (name) {
                /** Make sure we are not trying to re-image the Deployer **/
                if (localIps.indexOf(server['ip-addr']) >= 0) {
                    newServers[name] = states.COMPLETE;
                } else {
                    if (servers.hasOwnProperty(name)) {
                        if (servers[name] === states.ERROR) {
                            failedNodes.push(name);
                            newServers[name] = states.REMOVE;
                        } else if (servers[name] === states.PWR_ERROR) {
                            newServers[name] = states.READY;
                        } else {
                            newServers[name] = servers[name];
                        }

                        delete servers[name];
                    } else {
                        newServers[name] = states.READY;
                    }
                }
            }

            if (server._status) {
                delete server._status;
            }
        });
    }

    // Remove any nodes from cobbler system list if it was removed in UI
    var removedNodes = Object.keys(servers);
    if (removedNodes.length > 0) {
        failedNodes = failedNodes.concat(removedNodes);
    }

    servers = newServers;

    function imageServers() {
        /** Everything good so far, lets image servers now **/
        logger.debug('Re-imaging servers...');
        var imageServer = function(serverName) {
            var nodeStatus = servers[serverName];
            if (nodeStatus === states.READY || nodeStatus === states.REMOVE) {
                servers[serverName] = states.INSTALLING;
                return executeBmReImage(serverName).then(function() {
                    servers[serverName] = states.COMPLETE;
                }).catch(function(err) {
                    logger.error('Server ' + serverName + ' re-image failed due to: ' + err);
                    servers[serverName] = states.ERROR;
                    return Q.reject('Server ' + serverName + ' re-imaging failed!');
                });
            }
        };
        var promises = [];
        _.each(_.keys(servers), function(serverName) {
            promises.push(imageServer(serverName));
        });
        return Q.all(promises).then(function() {
            logger.info('OS Install on all servers was successful!');
        });
    }

    function makeCobblerErrorHandler(errorState, message) {
        return function(error) {
            logger.error(message + '. Error: ' + JSON.stringify(error));
            updateErrorStates(errorState);
            throw message;
        }
    }

    logger.debug('Installing HLinux on cloud nodes...');
    return executeCleanCommand(failedNodes, config).then(function() {
        return executeCobblerPowerStatus().then(function() {
            return executeCobblerDeployCommand(userPassword, disablePwdAuth)
                .then(imageServers, makeCobblerErrorHandler(states.ERROR, 'Cobbler Deploy failed'));
        }, makeCobblerErrorHandler(states.PWR_ERROR, 'BM Power status failed'));
    }, makeCobblerErrorHandler(states.ERROR, 'Clean Cobbler failed')); // NB: UI will think failed to img servers
}

function status() {

    var finished = true, hasError = false;
    for (var node in servers) {
        var nodeStatus = servers[node];
        if (nodeStatus !== states.COMPLETE &&
            nodeStatus !== states.ERROR &&
            nodeStatus !== states.PWR_ERROR) {
            finished = false;
        }

        if (nodeStatus === states.ERROR || nodeStatus === states.PWR_ERROR) {
            hasError = true;
        }
    }

    return {finished: finished, hasError: hasError, servers: servers};
}

function updateErrorStates(state) {
    var errState = state;
    _.each(_.keys(servers), function(server) {
        var status = servers[server];
        if (status === states.READY || status === states.REMOVE) {
            servers[server] = errState;
        }
    });
}

function initLocalIps() {
    /** Capture IPs of the Deployer Node **/
    var cmd = 'ip a | awk \'/inet / {sub("/.*","",$2) ; print $2}\'';
    return Q.nfcall(exec, cmd).then(function(processOutput) {
        /**
         * processOutput[0] -> stdout
         * processOutput[1] -> stderr
         */
        localIps = processOutput[0].trim().split('\n');
    });
}

/**
 * Clean up old failed node installs from Cobbler
 */
function executeCleanCommand(failedNodes, config) {

    var args = [];
    if (failedNodes) {
        args.push('-e');
        args.push('failed_nodes="' + failedNodes.join(',') + '"');
    }

    var ansiblePath = path.join(__dirname, '..', 'ansible');
    logger.debug('Running ready-install-os with arguments: ' + args + ' on path: ' + ansiblePath);
    return spawnAnsible(ansiblePath, 'ready-install-os.yml', args);
}

/**
 * Update Cobbler configuration
 */
function executeCobblerDeployCommand(userPassword, disablePwdAuth) {

    var opts = {};
    opts.extraVars = {};
    if (userPassword) {
        opts.extraVars.user_password = userPassword;
    }
    if (!_.isUndefined(disablePwdAuth)) {
        opts.extraVars.disable_pwd_auth = disablePwdAuth;
    }
    logger.debug('Running cobbler-deploy with arguments: ' + JSON.stringify(opts));
    return spawnAnsible(playbookDir, 'cobbler-deploy.yml', [], opts);
}

/**
 * Re-image named server
 */
function executeBmReImage(serverName) {

    var args = [];
    args.push('-e');
    args.push('nodelist="' + serverName + '"');

    logger.debug('Running bm-reimage on with arguments: ' + args);
    return spawnAnsible(playbookDir, 'bm-reimage.yml', args);
}

/**
 * Confirm iLO information is correct for servers
 */
function executeCobblerPowerStatus() {
    logger.debug('Running bm-power-status');
    return spawnAnsible(playbookDir, 'bm-power-status.yml');
}


function spawnAnsible(dir, playbookName, args, opts) {
    var spawnPromise = processManager.spawnAnsiblePlay(dir, 'hosts/localhost',
        playbookName, args, opts);
    return spawnPromise.then(function() {
        return spawnPromise.complete;
    });
}


/**
 * Initialise directories, fetch local IPs and write baremetal file
 */
module.exports.setup = setup;
/**
 * Run the ansible playbooks to re-image servers
 */
module.exports.install = install;
/**
 * Fetch status
 */
module.exports.status = status;
