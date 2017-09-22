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
var path = require('path');
var yaml = require('js-yaml');
var logger = require('./logger');
var ModelReader = require('../lib/model-reader');
var cache = require('../lib/template-cache');
var ModelWriter = require('../lib/model-writer');
var utils = require('./utils');
var treeUtils = require('./tree-utils');
var wrench = require('wrench');
var git = require('gift');
var Q = require('q');
var chokidar = require('chokidar');

var CONSTANTS = require('../lib/constants');

var statQ = Q.denodeify(fs.stat);
var readFileQ = Q.denodeify(fs.readFile);

var BAREMETAL_SERVERS = 'baremetal_servers';
var SERVERS = 'servers';
var CONTROL_PLANES = 'control-planes';
var SERVER_ROLES = 'server-roles';
var GIT_BRANCH = 'site';
var INPUT_MODEL = CONSTANTS.INPUT_MODEL;
var VAULT_MARKER = '$ANSIBLE_VAULT';
var CLOUD_MODEL_JSON = 'CloudModel.json';
var CLOUD_MODEL_YAML = 'CloudModel.yaml';

var SERVER_KEY = 'server';
var BAREMETAL_SERVER_KEY = 'baremetal_server';
var readyDeployTag = new RegExp('deployment-[0-9]{8,8}T[0-9]{6,6}Z-site');

/** globals **/
var giftInstance;
var currentInputModelPath;
var modelWriter;
var webSocketServer;
var config;

/** bound gift methods  for performance **/
var gitCheckoutQ;
var gitResetQ;
var gitStatusQ;
var gitHistoryQ;
var gitCurrentCommitQ;
//var gitBranchesQ;
var gitRefsQ;
var gitRemoveQ;
var gitAddQ;
var gitCommitQ;
var gitRevertQ;

// There can only be one writer at a time
var writerLock = Q.resolve();

// There can be many readers
var readers = [];

function collectDoneReaders() {
    for (var i = readers.length - 1; i >= 0; i--) {
        var promise = readers[i];
        if (!promise.isPending()) {
            logger.debug('Collected done reader at index: ' + i);
            readers.splice(i, 1);
        }
    }
}

function readLock(promiseReturningFunc) {
    // Wait until all writes are finished
    logger.debug('Acquiring model reader lock...');
    var readerDeferred = Q.defer();
    writerLock.finally(function() {
        logger.debug('Acquired model reader lock');
        var promise;
        // Cope with synchronous thrown by the promiseReturningFunc
        try {
            promise = promiseReturningFunc();
        } catch (error) {
            return readerDeferred.reject(error);
        }

        if (!promise) {
            logger.error('readLock was passed in a non promise returning function!');
            readerDeferred.resolve();
            return;
        }

        // Add ourselves to the readers
        readers.push(promise);
        promise.then(collectDoneReaders);

        readerDeferred.resolve(promise);
    });
    return readerDeferred.promise;
}

function writeLock(promiseReturningFunc) {

    if (writerLock.isPending()) {
        logger.error('Writer already locked! Concurrent writes to the model are not allowed');
        return Q.reject({
            isUserError: 'Concurrent writes to the model not allowed',
            statusCode: 403
        });
    }

    logger.debug('Acquiring model writer lock...');
    var writerDeferred = Q.defer();
    writerLock = writerDeferred.promise;

    Q.all(readers).finally(function() {
        logger.debug('Acquired model writer lock');
        var promise;
        // Cope with synchronous thrown by the promiseReturningFunc
        try {
            promise = promiseReturningFunc().then(function() {
                logger.debug('Released model writer lock');
            });
        } catch (error) {
            return writerDeferred.reject(error);
        }
        writerDeferred.resolve(promise);
    });

    return writerLock;

}

/** init function **/
function init(_config, _webSocketServer) {

    config = _config;
    /**
     * Read current config model
     */
    currentInputModelPath = path.normalize(config.get('paths:cloudDir'));
    logger.info('Using definition path: ' + currentInputModelPath);

    /** map of model file names to full path **/
    giftInstance = git(config.get('paths:ardanaDir'));

    gitCheckoutQ = Q.nbind(giftInstance.checkout, giftInstance);
    gitResetQ = Q.nbind(giftInstance.reset, giftInstance);
    gitStatusQ = Q.nbind(giftInstance.status, giftInstance);
    gitHistoryQ = Q.nbind(giftInstance.commits, giftInstance);
    gitCurrentCommitQ = Q.nbind(giftInstance.current_commit, giftInstance);
    gitRefsQ = Q.nbind(giftInstance.git.refs, giftInstance);
    gitRemoveQ = Q.nbind(giftInstance.remove, giftInstance);
    gitAddQ = Q.nbind(giftInstance.add, giftInstance);
    gitCommitQ = Q.nbind(giftInstance.commit, giftInstance);
    gitRevertQ = Q.nbind(giftInstance.revert, giftInstance);
    //gitBranchesQ = Q.nbind(cloudDirRepo.branches, cloudDirRepo);


    modelWriter = new ModelWriter(config);
    webSocketServer = _webSocketServer;

    if (config.get('notifyStateChanged')) {
        // We'll get notifications when server OR external parties change files.
        // Need to ensure we notify as soon as possible without flooding (so throttle requests). This will send one
        // notify when changes start, none for another second and another once updates finish (if 1+ changes received).
        // chokidar however can be too quick, changing a single file can result in two updates. So to avoid throttling
        // sending two notifies for single file changes debounce the update
        chokidar.watch([config.get('paths:cloudDir'), config.get('paths:cloudModelPath')], {
            ignoreInitial: true
        }).on('all', notifyClients);
    }
}

var throttleNotifyClients = _.throttle(lockedNotifyClients, 1000);
var debounceNotifyClients = _.debounce(throttleNotifyClients, 100);

function notifyClients() {
    return config.get('notifyStateChanged') ? debounceNotifyClients() : Q.resolve();
}

function unlockedNotifyClients() {
    var start = Date.now();
    logger.debug(start + ' Input Model state changed!');

    var _getStateAndLog = function() {
        return _getState(start).then(function(result) {
            logger.debug(Date.now() - start + 'ms getState');
            return result;
        }).catch(function(error) {
            // Stop chain if there's an error (no state to return to clients)
            logger.error('Failed to fetch state after file system change', error);
            throw error;
        });
    };

    return _getStateAndLog().then(function(state) {
        logger.debug(Date.now() - start + 'ms Stringifying state and model');
        var message = JSON.stringify({
            type: webSocketServer.MESSAGE_TYPES.INPUT_MODEL_CHANGE,
            state: state
        });
        logger.debug(Date.now() - start + 'ms Stringified state and model. Size: ' +
            (message.length / 1024).toFixed(1) + 'kB');

        for (var clientId in webSocketServer.webSocketClients) {
            if (!webSocketServer.webSocketClients.hasOwnProperty(clientId)) {
                continue;
            }

            var ws = webSocketServer.webSocketClients[clientId];
            ws.send(message, function(error) {
                logger.debug(Date.now() - start + 'ms sent to socket');
                if (error) {
                    logger.error('Failed to send message via the websocket', error);
                }
            });
        }
    }).catch(function(error) {
        //TODO: RC Notify clients that their model is out of date but error means local model/state hasn't been updated.
        // .. Check that errors while sending never end up here (don't warn of error to clients if already successfully
        // notified.
        logger.error('Failed to update clients following file system change', error);
    });
}

function lockedNotifyClients() {
    return readLock(function() {
        return unlockedNotifyClients();
    });
}


// Get model, not locked, internal use only
function _getModel() {
    return ModelReader.readTemplate(currentInputModelPath).then(function(model) {
        if (!model) {
            throw 'No model found!';
        } else if (model.errors.length !== 0) {
            _.forEach(model.errors, function(error) {
                logger.error(error);
            });
            throw 'Model contains errors!';
        }
        return model;
    });
}

// Read-locked model for external use
function getModel() {
    return readLock(function() {
        return _getModel();
    });
}

/**
 * Get Control Plane information
 */
function getControlPlanes() {
    return readLock(function() {
        return _getModel().then(function(model) {
            return model[INPUT_MODEL][CONTROL_PLANES];
        });
    });
}

function getControlPlane(controlPlaneName) {
    return readLock(function() {
        return _getModel().then(function(model) {

            var controlPlane = _.find(model[INPUT_MODEL][CONTROL_PLANES], function(item) {
                return item.name === controlPlaneName;
            });

            if (!controlPlane) {
                throw {isUserError: 'Unable to find ' + controlPlaneName + ' control plane in the model!'};
            }
            return controlPlane;
        });
    });
}

function addCluster(controlPlaneName, cluster) {

    if (!controlPlaneName || !cluster) {
        return Q.reject({isUserError: 'Invalid parameters supplied to add cluster'});
    }

    return writeLock(function() {
        return _getModel().then(function(model) {

            var plane = _.find(model[INPUT_MODEL][CONTROL_PLANES], function(item) {
                return item.name === controlPlaneName;
            });
            if (!plane) {
                return Q.reject({isUserError: 'Can not find control plane with name: ' + controlPlaneName});
            }

            // Append the cluster to the Control Plane
            if (!plane.clusters) {
                plane.clusters = [];
            }

            plane.clusters.push(cluster);

            return _writeModel(model);
        });
    });

}

function _getServers() {
    return _getModel().then(function(model) {
        var baremetal_servers = null;
        if (_.has(model[INPUT_MODEL], BAREMETAL_SERVERS)) {
            baremetal_servers = model[INPUT_MODEL][BAREMETAL_SERVERS];
        }
        var servers = model[INPUT_MODEL][SERVERS];
        return _.values(ServerUtils.mergeServerData(baremetal_servers, servers));
    });
}

/**
 * Get Merged Server information
 */
function getServers() {
    return readLock(function() {
        return _getServers();
    });
}


/**
 * Validate submitted server information
 */
function validateServer(serverData, checkIfExists) {
    return readLock(function() {
        return _getServers().then(function(servers) {

            var serversFileRequiredKeys = ['id', 'ip-addr', 'role'];
            if (!hasFields(serverData, 'server', serversFileRequiredKeys)) {
                var error = 'Server is missing one or more required fields... ' + serversFileRequiredKeys;
                throw {isUserError: error};
            }

            if (checkIfExists) {
                var foundServer = false;
                _.each(servers, function(server) {
                    if (!foundServer && _.has(server, SERVER_KEY)) {
                        if (ServerUtils.getId(server[SERVER_KEY]) === ServerUtils.getId(serverData[SERVER_KEY])) {
                            foundServer = 'IP/MAC identity';
                        } else if (server[SERVER_KEY].id === serverData[SERVER_KEY].id) {
                            foundServer = 'Id';
                        }
                    }
                });

                if (foundServer) {
                    throw {isUserError: 'Found existing server with same ' + foundServer};
                }
            }
        });
    });
}


function _addServerToModel(serverData) {
    return _getModel().then(function(model) {

        // Update bare metal file, if server with the ID already exists, override it
        if (_.has(serverData, BAREMETAL_SERVER_KEY)) {
            model[INPUT_MODEL].baremetal_servers.push(serverData[BAREMETAL_SERVER_KEY]);
        }

        // Update servers file
        // If this is an undelete then try and put the server in the correct place
        var preservePosition = serverData[SERVER_KEY].$preservePosition;
        delete serverData[SERVER_KEY].$preservePosition;
        if (!preservePosition) {
            model[INPUT_MODEL].servers.push(serverData[SERVER_KEY]);
        } else {
            model[INPUT_MODEL].servers.splice(preservePosition, 0, serverData[SERVER_KEY]);
        }

        return model;
    });
}

function _addServer(newServerData) {
    return _addServerToModel(newServerData).then(_writeModel);
}

/**
 * Add Server
 */
function addServer(newServerData) {
    return writeLock(function() {
        return _addServer(newServerData);
    });
}


/**
 * Update Server
 */
function updateServer(serverId, data) {
    return writeLock(function() {
        return _getModel()
            .then(_.partial(_deleteServer, serverId))
            .then(_getModel)
            .then(_.partial(_addServer, data));
    });
}


function _deleteServer(serverId, model) {
    /** NOTE: don't delete baremetal definition, only update servers.yml **/

    var deleteBareMetal = false;
    var updatedSections = [];

    var deleteServerEntry = function() {
        var serversArray = model[INPUT_MODEL].servers;
        var newServersArray = [];
        var internalId = null;
        _.each(serversArray, function(server) {
            if (server.id != serverId) {
                newServersArray.push(server);
            } else {
                internalId = ServerUtils.getId(server);
            }
        });
        model[INPUT_MODEL].servers = newServersArray;
        updatedSections.push('servers');
        return internalId;
    };

    var deleteBaremetalEntry = function(internalId) {

        if (!deleteBareMetal) {
            return;
        }

        var baremetalArray = model[INPUT_MODEL].baremetal_server;
        var newBaremetalArray = [];
        _.each(baremetalArray, function(server) {
            if (ServerUtils.getId(server) != internalId) {
                newBaremetalArray.push(server);
            }
        });
        model[INPUT_MODEL].baremetal_servers = newBaremetalArray;
        updatedSections.push('baremetal_servers');
    };


    var internalId = deleteServerEntry();
    if (!internalId) {
        throw {isUserError: 'Server ' + serverId + ' not found in servers section!'};
    }
    deleteBaremetalEntry(internalId);

    return _writeModel(model);
}

function deleteServer(serverId, model) {
    return writeLock(function() {
        return _deleteServer(serverId, model);
    });
}


/*
 * Spare Servers - Defined in bare metal but not in server
 * */
function getAvailableServers(currentInputModel) {
    // At some point the baremetal file will disappear. When that happens fall back on the servers we know to be there.
    // In the future this will be provided by external means
    var allServers =
        _.get(currentInputModel[INPUT_MODEL], 'baremetal_servers') ||
        [
            {
                node_name: 'spn01',
                role: 'default',
                pxe_mac_addr: 'fa:54:00:c9:5a:a0',
                pxe_interface: 'eth2',
                pxe_ip_addr: '192.168.10.30',
                ilo_ip: '192.168.9.9',
                ilo_user: 'admin',
                ilo_password: 'password'
            },
            {
                node_name: 'spn02',
                role: 'default',
                pxe_mac_addr: 'fa:54:00:c9:5a:a1',
                pxe_interface: 'eth2',
                pxe_ip_addr: '192.168.10.31',
                ilo_ip: '192.168.9.10',
                ilo_user: 'admin',
                ilo_password: 'password'
            },
            {
                node_name: 'spn03',
                role: 'default',
                pxe_mac_addr: 'fa:54:00:c9:5a:a2',
                pxe_interface: 'eth2',
                pxe_ip_addr: '192.168.10.31',
                ilo_ip: '192.168.9.11',
                ilo_user: 'admin',
                ilo_password: 'password'
            }
        ];
    var serversArray = currentInputModel[INPUT_MODEL][SERVERS];

    var availableServers = _.reject(allServers, function(baremetal) {
        return _.find(serversArray, function(server) {
            return ServerUtils.getId(baremetal, true) === ServerUtils.getId(server);
        });
    });

    return _.map(availableServers, function(baremetal) {
        return {
            baremetal_server: baremetal
        };
    });
}

/** TODO needs to be updated when roles are supported in the frontend **/
function getServerRoles() {

    //return _.get(currentInputModel[INPUT_MODEL], SERVER_ROLES) || [];
    return [{
        name: 'COMPUTE-ROLE',
        'interface-model': 'COMPUTE-INTERFACES',
        'disk-model': 'COMPUTE-DISKS'
    }];
}

function hasFields(data, rootKey, keys) {

    var hasAllFields = true;
    if (_.has(data, rootKey)) {
        _.each(keys, function(key) {
            if (hasAllFields) {
                hasAllFields = _.has(data[rootKey], key);
            }
        });
    }
    return hasAllFields;
}

function _isEncrypted() {
    // Check if the group_vars are encrypted
    var allVarsFile = path.join(config.get('paths:scratchDir'), 'group_vars', 'all');
    return fileExists(allVarsFile).then(function(exists) {
        if (exists) {
            var buffer = new Buffer(VAULT_MARKER.length);
            return Q.nfcall(fs.open, allVarsFile, 'r').then(function(fd) {
                // N.B. I never saw .read() return less than VAULT_MARKER.length bytes so one call is enough
                return Q.nfcall(fs.read, fd, buffer, 0, VAULT_MARKER.length, null).then(function() {
                    var marker = buffer.toString('utf8');
                    return marker === VAULT_MARKER;
                }).finally(function() {
                    fs.close(fd);
                });
            }).catch(function(error) {
                // We have no idea if it's encrypted here
                logger.error(error);
                throw error;
            });
        }
        return false;
    });
}

function isEncrypted() {
    return readLock(function() {
        return _isEncrypted();
    });
}

/**
 * Look for a server by ID in serverGroups
 * @return {Object} the server Object or undefined if not found
 * */
function _findServer(serverGroups, serverId) {
    /// In 3.0 all server groups (including leaf groups) are also in the top-level array so no need to recurse
    for (var i = 0; i < serverGroups.length; i++) {
        var serverGroup = serverGroups[i];
        if (serverGroup.hasOwnProperty('servers')) { // Only go through leaf groups
            var servers = serverGroup.servers;
            for (var j = 0; j < servers.length; j++) {
                var server = servers[j];
                if (server.id === serverId) {
                    return server;
                }
            }
        }
    }
}

function _writeModel(newInputModel) {
    //return modelWriter.writeModel(newInputModel).delay(5000); // easier to debug locks with artificial delay
    return modelWriter.writeModel(newInputModel);
}

/** Replace current input model **/
function writeModel(newInputModel) {
    return writeLock(function() {
        return _writeModel(newInputModel);
    });
}

function fileExists(filePath) {
    return statQ(filePath).then(function(stats) {
        return stats.isFile();
    }).catch(function() {
        return false;
    });
}

/**
 * 1. get template cache, check if it exists
 * 2. copy to mycloud
 * 3. return
 */
function setTemplate(modelName) {

    if (!_.includes(cache.templateNames, modelName)) {
        return Q.reject({err: 'Model ' + modelName + ' does not exist!'});
    }

    return writeLock(function() {
        var templatePath = path.join(config.get('paths:templatesDir'), modelName);
        var myCloudModelPath = config.get('paths:cloudDir');
        return Q.nfcall(wrench.copyDirRecursive, templatePath, myCloudModelPath, {forceDelete: true});
    });

}

/**
 * Check if changes have been made to the current model
 * Returns:  { staged: [..], unstaged: [..], untracked: [..] }
 */
function _getStatus() {
    return gitStatusQ();
}

function getStatus() {
    return readLock(function() {
        return _getStatus();
    });
}

/**
 * Check if changes have been made to the current model
 * Returns:  { staged: [..], unstaged: [..], untracked: [..] }
 */
function getHistory(count) {
    return readLock(function() {
        return gitHistoryQ(GIT_BRANCH, count || 100);
    });
}

/**
 * Get State
 * Returns:
 */
function _getState(start) {

    if (!start) {
        start = Date.now();
    }

    function logComplete(func, name) {
        return func().then(function(result) {
            logger.debug(Date.now() - start + 'ms ' + name);
            return result;
        }, function(err) {
            logger.error('getState request failed: ' + name);
            return Q.reject(err);
        });
    }

    return Q.all([
        logComplete(_getStatus, 'getStatus'),
        logComplete(_getCurrentCommit, 'getCurrentCommit'),
        logComplete(_getSiteCommit, 'getSiteCommit'),
        logComplete(_getTags, 'getTags')]).spread(
        function(status, currentCommit, siteCommit, tags) {
            var incorrectHead, isModified, commitReadyToReady;

            // Are we in detached HEAD state?
            var branchHeadId = _.get(siteCommit, 'id', '');
            incorrectHead = branchHeadId !== _.get(currentCommit, 'id');

            if (!incorrectHead) {
                // Have any input model files been modified?
                isModified = !status.clean;

                // Is the commit at head of 'site' without a 'deployment-x' tag?
                commitReadyToReady = true;

                var tags = tags || [];
                for (var i = 0; i < tags.length; i++) {
                    var tag = tags[i];
                    if (tag.commit.id === branchHeadId) {
                        commitReadyToReady = !readyDeployTag.test(tag.name);
                        break;
                    }
                }
            }

            var responseObj = {};
            // Determine the input model state from the above conditions
            if (incorrectHead) {
                responseObj = {
                    name: 'incorrectHead',
                    validEndpoints: []
                };
            } else if (isModified && commitReadyToReady) {
                responseObj = {
                    name: 'modifiedAndCommitted',
                    validEndpoints: ['/playbooks/site', '/config_processor', '/model/commit']
                };
            } else if (isModified) {
                responseObj = {
                    name: 'modified',
                    validEndpoints: ['/playbooks/site', '/config_processor', '/model/commit']
                };
            } else if (commitReadyToReady) {
                responseObj = {
                    name: 'committed',
                    validEndpoints: ['/playbooks/site', '/playbooks/ready_deployment']
                };
            } else {
                responseObj = {
                    name: 'clean',
                    validEndpoints: ['/playbooks/site']
                };
            }
            return responseObj;
        });
}

function getState(start) {
    return readLock(function() {
        return _getState(start);
    });
}

function _getSiteCommit() {
    // Note this is currently not requiring locking
    return gitHistoryQ(GIT_BRANCH, 1).then(function(commits) {
        return commits && commits.length > 0 ? commits[0] : null;
    });
}

function getSiteCommit() {
    return readLock(function() {
        return _getSiteCommit();
    });
}

function _getCurrentCommit() {
    return gitCurrentCommitQ();
}

function getCurrentCommit() {
    return readLock(function() {
        return _getCurrentCommit();
    });
}

function _getTags() {

    // Previously used 'this.cloudDirRepo.tags' to get tag data which fetched all tags with their
    // commit id's (.git.refs) and then found all commit metadata associated with those id's (Commit.find_commits).
    // The later takes a considerable time (1s+), so skip it by manually executing .git.refs and transforming text as
    // per Ref.find_all.
    return gitRefsQ('tag').then(function(text) {
        var tags = [], id, j, len, name, ref, ref1, ref2;
        ref1 = text.split('\n');
        for (j = 0, len = ref1.length; j < len; j++) {
            ref = ref1[j];
            if (!ref) {
                continue;
            }
            ref2 = ref.split(' '), name = ref2[0], id = ref2[1];
            tags.push({
                name: name,
                commit: {
                    id: id
                }
            });
        }
        return tags;
    });
}

function getTags() {
    return readLock(function() {
        return _getTags();
    });
}

function _stageAllChanges(changes) {
    logger.info('Staging all changes...');

    var keys = _.keys(changes.files);

    if (keys.length === 0) {
        return Q.reject({
            isUserError: 'No changes to stage',
            code: CONSTANTS.ERROR_CODES.COMMIT_NO_CHANGES.code
        });
    }

    function _makeProcessChangeFunc(file) {
        return function() {
            logger.debug('Staging file: ' + file);
            if (changes.files[file].type === 'D') {
                return gitRemoveQ(file);
            }
            return gitAddQ(file);
        }
    }

    // Create an array of functions that return a promise
    var funcs = _.map(keys, _makeProcessChangeFunc);

    // Chain the above functions together
    return funcs.reduce(Q.when, Q());
}

/**
 * Stage and commit any unstaged changes
 */
function commit(message) {

    if (_.isUndefined(message) || message.length === 0) {
        return Q.reject({isUserError: 'Commit message is missing'});
    }

    // Git commit and resolve with the newly made commit
    var _commit = function() {
        logger.info('Committing changes');
        return gitCommitQ(message).then(_getCurrentCommit);
    };

    return writeLock(function() {
        return _isBranchHead()
            .then(_getStatus)
            .then(_stageAllChanges)
            .then(_commit)
            .then(function(commitId) {
                unlockedNotifyClients();
                return commitId;
            })
            .catch(function(err) {
                return Q.reject(err);
            });
    });
}

/** Clean Openstack directory **/
function cleanRepo() {

    logger.info('Cleaning input model directory');

    function _cleanChange(repo_status, fileName) {

        logger.debug('Resetting change to file: ' + fileName);
        var fileMetadata = repo_status.files[fileName];
        if (fileMetadata.tracked) {
            // If it was deleted or modified, checkout the file
            if (fileMetadata.type === 'D' || fileMetadata.type === 'M') {
                logger.log('Checking out file: ' + fileName);
                return gitCheckoutQ(fileName);
            } else if (fileMetadata.type == 'A') {
                logger.log('Resetting file: ' + fileName);
                return gitResetQ(fileName).then(function() {
                    logger.log('Deleting file: ' + fileName);
                    return Q.nfcall(fs.unlink, path.join(giftInstance.path, fileName));
                });
            }

        } else {
            // File is not tracked, delete it
            logger.debug('Deleting untracked file: ' + fileName);
            return Q.nfcall(fs.unlink, path.join(giftInstance.path, fileName));
        }
    }

    function _unstageAll() {
        logger.debug('Unstaging all changes in my_cloud directory');
        return gitResetQ();
    }

    function _unsetChanges(repo_status) {
        logger.debug('Building chain of promises...');
        var files = _.keys(repo_status.files);
        var initialPromise = null;
        _.forEach(files, function(file) {
            logger.debug('Adding promise to unset changes in file: ' + file);
            if (!initialPromise) {
                initialPromise = _cleanChange(repo_status, file);
                return;
            }
            initialPromise = initialPromise.then(_.partial(_cleanChange, repo_status, file));
        });
        return initialPromise;
    }

    return writeLock(function() {
        return _isBranchHead()
            .then(_unstageAll)
            .then(_getStatus)
            .then(_unsetChanges);
    });
}

/**
 *  Revert Input Model commit
 * **/
function _revert(commitId) {
    var _giftRevert = function() {
        // First entrance, get the previous commit
        if (!commitId) {
            return _getSiteCommit().then(function(commit) {
                commitId = commit.id;
                return _giftRevert(commitId);
            });
        }
        // Re-entrance, revert to the previous commit
        return gitHistoryQ().then(function(commits) {
            for (var i = 0; i < commits.length; i++) {
                if (commits[i].id !== commitId) {
                    return gitRevertQ(commitId);
                }
            }
        });
    };
    return _isBranchHead().then(_giftRevert);
}

function revert(commitId) {
    return writeLock(function() {
        return _revert(commitId);
    });
}

function _isBranchHead() {
    return Q.all([_getCurrentCommit(), _getSiteCommit()]).spread(function(currentCommit, siteCommit) {
        if (currentCommit.id !== siteCommit.id) {
            return Q.reject({isUserError: 'git HEAD does not match branch site HEAD'});
        }
    });
}

function isBranchHead() {
    return readLock(function() {
        return _isBranchHead();
    });
}

// List and retrieve CP output entities
function getCPOutputEntity(entityName, dir) {

    var dirPath = dir ? dir : config.get('paths:readyCpOutputDir');
    // Always scan
    return treeUtils.scanDirectory(dirPath).then(function(allEntities) {
        allEntities = utils.sortKeys(allEntities);
        var subTree = treeUtils.getRelevantSubtree(entityName, allEntities);
        if (treeUtils.isLeaf(subTree)) { // A leaf! Return the file contents
            return readFileQ(subTree._path_, 'utf8').then(function(bytes) {
                if (utils.endsWith(subTree._path_, 'yml')) {
                    try {
                        return {
                            parsedEntity: yaml.safeLoad(bytes)
                        };
                    } catch (ignored) {
                    }
                }
                return {
                    unparseable: true,
                    bytes: bytes,
                    mtime: subTree._mtime_.toUTCString()
                };
            });
        }
        return {
            isNotLeaf: true,
            subTree: treeUtils.nullTerminateLeaves(subTree)
        };
    });
}


var ServerUtils = {

    getId: function(server, baremetal) {
        if (baremetal) {
            return server['pxe_ip_addr'] + '_' + server['pxe_mac_addr'];
        }
        return server['ip-addr'] + '_' + server['mac-addr'];
    },


    mergeServerData: function(baremetal_servers, servers) {

        var tmp_servers = {};
        _.each(servers, function(server) {
            var id = ServerUtils.getId(server);
            tmp_servers[id] = {};
            tmp_servers[id].server = server;
        });
        /** baremetal files are optional **/
        if (baremetal_servers) {
            _.each(baremetal_servers, function(baremetal_server) {

                var serverId = ServerUtils.getId(baremetal_server, true);
                if (!_.has(tmp_servers, serverId)) {
                    /** we have found a baremetal_server that is present
                     * in the baremetal file but not in the servers file **/
                    tmp_servers[serverId] = {};
                }
                tmp_servers[serverId].baremetal = baremetal_server;
            });
        }
        return tmp_servers;
    }

};

/** Server Operations */
module.exports.getServers = getServers;
module.exports.validateServer = validateServer;
module.exports.addServer = addServer;
module.exports.deleteServer = deleteServer;
module.exports.updateServer = updateServer;

module.exports.getAvailableServers = getAvailableServers;
module.exports.getServerRoles = getServerRoles;

/** Control Plane Operations */
module.exports.getControlPlanes = getControlPlanes;
module.exports.getControlPlane = getControlPlane;
module.exports.addCluster = addCluster;

//
/** Model operations **/
module.exports.getModel = getModel;
module.exports.setTemplate = setTemplate;
module.exports.isEncrypted = isEncrypted;
module.exports.writeModel = writeModel;
module.exports.getIdKey = ModelReader.getIdKey;
//
/** Commit model changes **/
module.exports.commit = commit;
module.exports.getStatus = getStatus;
module.exports.clean = cleanRepo;
module.exports.getState = getState;
module.exports.revert = revert;
module.exports.getHistory = getHistory;
module.exports.getSiteCommit = getSiteCommit;
module.exports.getCurrentCommit = getCurrentCommit;
//module.exports.gitBranches = gitBranchesQ;
module.exports.getTags = getTags;
module.exports.isBranchHead = isBranchHead;
module.exports.getCPOutputEntity = getCPOutputEntity;

/** Internal functions **/
//module.exports.storeDefinition = storeDefinition;

/** Notifications **/
module.exports.notifyClients = notifyClients;

module.exports.init = init;
