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
exports.runPlaybook = runPlaybook;

var fs = require('fs');
var _ = require('lodash');
var Q = require('q');
var path = require('path');
var yaml = require('js-yaml');

var utils = require('../lib/utils');
var constants = require('../lib/constants');
var processManager = require('../lib/process-manager');
var logger = require('../lib/logger');
var currentInputModel = require('../lib/current-input-model');

var ANSIBLE_DIR = 'openstack/ardana/ansible/';
var SCRATCH_DIR = 'scratch/ansible/next/ardana/ansible';
var PLAYBOOKS_PATH = '/playbooks';
var VAULT_PASSWORD_FILE = '.vault-pwd';

var preventConcurrentRuns = ['site.yml', 'ready_deployment.yml'];

var readdirQ = Q.denodeify(fs.readdir);
var writeFileQ = Q.denodeify(fs.writeFile);
var unlinkQ = Q.denodeify(fs.unlink);

// These special playbooks are run directly from ANSIBLE_DIR (not the readied scratch dir)
var STATIC_PLAYBOOKS = {
    config_processor_run: 'config-processor-run.yml',
    config_processor_clean: 'config-processor-clean.yml',
    ready_deployment: 'ready-deployment.yml'
};

var globalScanningPromise = Q.resolve();
var allPlaybooks = {};

// The following variables are set from the config during init()
var remoteDeployer, sshPort;
var vaultPasswordPath;
var homePath;
var isStandalone;
var playbooksDirectories;

function preventConcurrentRun(playbookName) {
    return _.includes(preventConcurrentRuns, playbookName);
}

// Remove '.yml' extension and turn dashes to underscores
function normalisePlaybookName(playbook) {
    var ret = playbook.toLowerCase();
    if (utils.endsWith(ret.toLowerCase(), '.yml')) {
        ret = ret.slice(0, -4);
    }
    // For now carry on with our convention that we replace dashes with underscores
    // I'm happy to drop this at anytime
    ret = ret.replace(/-/g, '_');
    return ret;
}

function addPlaybooks(playbookFiles, playbookDir) {
    if (_.isArray(playbookFiles)) {
        for (var i = 0; i < playbookFiles.length; i++) {
            addPlaybooks(playbookFiles[i], playbookDir);
        }
        return;
    }
    allPlaybooks[normalisePlaybookName(playbookFiles)] = {
        playbookDir: playbookDir,
        playbookFile: playbookFiles
    };
}

// Extract relevant *verbs* playbooks from the top level playbooks
function refreshPlaybooks() {

    // Avoid concurrent refreshing of playbooks
    if (globalScanningPromise.isPending()) {
        return globalScanningPromise;
    }

    logger.debug('Refreshing dynamic playbooks');

    // Reset allPlaybooks
    allPlaybooks = _.clone(STATIC_PLAYBOOKS);

    var allScanningPromises = [];
    _.forEach(playbooksDirectories, function(playbooksDir) {
        // If a relative path was passed in, it means relative to homePath
        if (!path.isAbsolute(playbooksDir)) {
            playbooksDir = path.join(homePath, playbooksDir);
        }
        try {
            var stats = fs.statSync(playbooksDir);
            if (!stats.isDirectory()) {
                logger.error("Playbooks directory '" + playbooksDir + "' is not a directory! Aborting scan");
                allScanningPromises.push(Q.resolve({
                    playbookFiles: [],
                    playbooksDir: playbooksDir
                }));
                return;
            }
        } catch (error) {
            logger.warn("Playbooks directory '" + playbooksDir + "' doesn't exist. " +
                "This could indicate that the ready_deployment playbook hasn't been run yet. " +
                'The list of playbooks available will be reduced');
            allScanningPromises.push(Q.resolve({
                playbookFiles: [],
                playbooksDir: playbooksDir
            }));
            return;
        }

        allScanningPromises.push(readdirQ(playbooksDir).then(function(allFiles) {
            var playbookFiles = allFiles.filter(function(file) {
                // Skip playbooks that start with an underscore
                if (file.indexOf('_') === 0) {
                    return false;
                }
                // Return all .yml files
                return utils.endsWith(file.toLowerCase(), '.yml');
            });

            return {
                playbookFiles: playbookFiles,
                playbooksDir: playbooksDir
            };

        }));
    });

    globalScanningPromise = Q.all(allScanningPromises).then(function(scannedDirectories) {
        // Add them in order from the config (last entry takes precedence in case of name collisions)
        _.forEach(scannedDirectories, function(scannedDir) {
            addPlaybooks(scannedDir.playbookFiles, scannedDir.playbooksDir);
        });
        // Finally, sort all playbooks alphabetically for better readability
        allPlaybooks = utils.sortKeys(allPlaybooks);
        return allPlaybooks;
    });

    return globalScanningPromise;
}

function stringToHash(hash) {
    return function(kvPair) {
        var index = kvPair.indexOf('=');
        if (index < 0) {
            throw {
                isUserError: "Invalid key-value pair detected in extraVars: '" + kvPair + "'",
                statusCode: 400
            };
        }
        var key = kvPair.slice(0, index);
        var value = kvPair.slice(index + 1);
        if (!key) {
            throw {
                isUserError: "null key detected in extraVars: '" + kvPair + "'",
                statusCode: 400
            };
        }
        hash[key] = value;
    }
}

function init(router, config) {

    homePath = config.get('homePath');
    isStandalone = config.get('isStandalone');
    vaultPasswordPath = path.join(config.get('paths:scratchDir'), VAULT_PASSWORD_FILE);
    remoteDeployer = config.get('deployer:remote');
    sshPort = config.get('deployer:sshPort') || '22';
    playbooksDirectories = config.get('playbooks:scanDirs');

    // Eagerly refresh playbooks, because we can
    refreshPlaybooks();

    // List available playbooks - always refreshes the list from the filesystem
    router.get(PLAYBOOKS_PATH, function(request, response) {
        refreshPlaybooks().then(function(playbooks) {
            response.json(Object.keys(playbooks));
        });
    });

    // Run a playbook
    router.post(PLAYBOOKS_PATH + '/:playbook', function(request, response) {
        var playbook = request.params.playbook;
        var playbookKey = normalisePlaybookName(playbook);
        var opts = {
            clientId: request.headers.clientid,
            tags: request.body.tags,
            skipTags: request.body.skipTags,
            noColor: request.body.noColor,
            extraVars: request.body.extraVars
        };

        switch (playbookKey) {
            case 'site':
                _.assign(opts, {
                    limit: request.body.limit,
                    encryptionKey: request.body.encryptionKey,
                    keepDayZero: request.body.keepDayZero,
                    destroyDayZeroOnSuccess: request.body.destroyDayZeroOnSuccess
                });
                break;
            case 'config_processor_run':
                _.assign(opts, {
                    encryptionKey: request.body.encrypt || '',
                    newEncryptionKey: request.body.rekey || '',
                    removeDeletedServers: request.body.removeDeletedServers,
                    freeUnusedAddresses: request.body.freeUnusedAddresses
                });
                break;
            case 'config_processor_clean':
            case 'ready_deployment':
                break;
            default:
                // All other playbooks
                _.assign(opts, {
                    limit: request.body.limit,
                    encryptionKey: request.body.encryptionKey,
                    inventoryFile: request.body.inventoryFile
                });
        }

        try {
            var spawnPromise = runPlaybook(playbook, opts);
            handleAsyncSpawn(spawnPromise, response);
        } catch (error) {
            // We need to handle synchronous errors here
            logger.error('Failed to spawn playbook \'' + playbook + '\'. ', error);
            utils.sendErrorResponse(response, error);
        }
    });
}

/**
 * Run an Ansible playbook
 * @param {Object=} opts additional options described below
 *        {boolean=} opts.noColor - disable colors in ansible logs
 *        {string=} opts.limit value for the '--limit' playbook argument
 *        {string=} opts.tags value for the '--tags' playbook argument
 *        {string=} opts.skipTags value for the '--skip-tags' playbook argument
 *        {string=} opts.clientId opaque identifier of the caller
 *        {Object=} opts.extraVars value for the '--extra-vars' playbook argument
 * */
function runPlaybook(playbook, opts) {

    var playbookKey = normalisePlaybookName(playbook);

    // Make sure extraVars is a Hash
    var extraVars = opts.extraVars || {};
    var objVars;
    // Turn space separated Strings of key=value pairs into Object key -> value
    if (_.isString(extraVars)) {
        logger.debug('Turning space separated Strings of key=value pairs into Object key -> value...');
        objVars = {};
        _.forEach(extraVars.split(' '), stringToHash(objVars));
        extraVars = objVars;
    } else if (_.isArray(extraVars)) {
        // Also support arrays of the above Strings
        logger.debug('Turning Array of key=value pairs into Object key -> value...');
        objVars = {};
        _.forEach(extraVars, function(kvPairs) {
            // Also support multiple space separated values in the array
            _.forEach(kvPairs.split(' '), stringToHash(objVars));
        });
        extraVars = objVars;
    }

    // Finally, guard against unexpected types
    if (!_.isPlainObject(extraVars)) {
        throw {
            isUserError: "Received the following non plain Object as extraVars '" +
            JSON.stringify(extraVars) + "'",
            statusCode: 400
        };
    }

    // Assign extra-vars back
    opts.extraVars = extraVars;

    switch (playbookKey) {
        case 'site':
            return runSite(opts);
        case 'config_processor_run':
            return runConfigProcessor(opts);
        case 'config_processor_clean':
            return runConfigProcessorClean(opts);
        case 'ready_deployment':
            return runReadyDeployment(opts);
        default:
            // All other playbooks

            // Check if the playbook is already in our collection
            var maybeDelayStart;
            if (allPlaybooks.hasOwnProperty(playbookKey)) {
                logger.debug('Playbook ' + playbook + ' found in the list :D');
                maybeDelayStart = false;
            } else {
                logger.debug('Playbook ' + playbook + ' not found in the list :(');
                // Note this is smart enough not to trigger multiple refreshes in parallel
                maybeDelayStart = refreshPlaybooks();
            }

            var completionDeferred = Q.defer();
            var returnedPromise = Q.when(maybeDelayStart)
                .then(function() {
                    if (allPlaybooks.hasOwnProperty(playbookKey)) {
                        return allPlaybooks[playbookKey].playbookFile;
                    }
                    throw {
                        statusCode: 404,
                        isUserError: "Playbook '" + playbook + "' not available"
                    };
                })
                .then(function(playbookFile) {
                    opts.playbookDir = allPlaybooks[playbookKey].playbookDir;
                    var spawnPromise = startPlaybook(playbookFile, opts);

                    // Forward the state of the completion promise
                    spawnPromise.complete.then(function(resolution) {
                        completionDeferred.resolve(resolution);
                    }, function(rejection) {
                        completionDeferred.reject(rejection);
                    });

                    return spawnPromise;
                })
                .catch(function(error) {
                    completionDeferred.reject(error);
                    throw error;
                });

            returnedPromise.complete = completionDeferred.promise;
            return returnedPromise;
    }
}

/**
 * Execute the config-processor-run playbook
 * @param {Object=} opts additional options described below
 *            {string=} opts.encryptionKey configuration process encryption key
 *            {string=} opts.newEncryptionKey if the encryption key needs to be changed, this is the new key
 *            {boolean=} opts.removeDeletedServers execute the playbook with the remove_deleted_servers flag
 *            {boolean=} opts.freeUnusedAddresses execute the playbook with the free_unused_addresses flag
 *            {string=} opts.clientId identifier for the initiator of the process
 * @returns {object} A promise object which completes once config-processor-run STARTS.
 * The object contains a 'complete' property which contains a promise resolved when the playbook finishes
 */
function runConfigProcessor(opts) {

    // Ensure opts are optional
    opts = opts || {};

    // Cope with null/undefined keys by mapping to empty strings
    opts.encryptionKey = opts.encryptionKey || '';
    opts.newEncryptionKey = opts.newEncryptionKey || '';

    // Inherit spawnOpts from passed opts (except things handled locally)
    var spawnOpts = _.omit(opts, [
        'args',
        'encryptionKey',
        'newEncryptionKey',
        'removeDeletedServers',
        'freeUnusedAddresses'
    ]);

    // Ensure we don't run concurrent CPs
    spawnOpts.preventConcurrentRuns = true;

    // Populate extra vars appropriately
    spawnOpts.extraVars = spawnOpts.extraVars || {};
    spawnOpts.extraVars['encrypt'] = opts.encryptionKey;
    spawnOpts.extraVars['rekey'] = opts.newEncryptionKey;
    if (opts.removeDeletedServers) {
        spawnOpts.extraVars['remove_deleted_servers'] = true;
    }
    if (opts.freeUnusedAddresses) {
        spawnOpts.extraVars['free_unused_addresses'] = true;
    }

    // Using SSHFS nanotime precision is lost which causes git to think that the index is dirty on the remote
    var gitStatusFixer;
    if (remoteDeployer) {
        logger.debug("Trigger remote 'git status' to fix git index nanotime...");
        gitStatusFixer = processManager.spawnProcess('', 'ssh',
            ['-p ' + sshPort, 'stack@' + remoteDeployer, 'cd openstack && git status'],
            {
                description: 'fix git index nanotime',
                internal: true,
                clientId: opts.clientId
            })
            .complete.then(
                function() {
                    logger.debug('Remote status succeeded');
                },
                function(error) {
                    throw {error: error, message: 'Fixing git index nanotime failed'};
                });
    } else {
        gitStatusFixer = true;
    }

    var completionDeferred = Q.defer();
    var returnedPromise = Q.when(gitStatusFixer, function() {
        var spawnPromise = processManager.spawnAnsiblePlay(ANSIBLE_DIR, 'hosts/localhost',
            'config-processor-run.yml', opts.args, spawnOpts);

        // Forward the state of the completion promise
        spawnPromise.complete.then(function(resolution) {
            completionDeferred.resolve(resolution);
        }, function(rejection) {
            completionDeferred.reject(rejection);
        });

        return spawnPromise;
    }).catch(function(error) {
        completionDeferred.reject(error);
        throw error;
    });

    returnedPromise.complete = completionDeferred.promise;
    return returnedPromise;
}

function runConfigProcessorClean(opts) {
    // Ensure opts are optional
    opts = opts || {};

    // Inherit spawnOpts from passed opts (except things handled locally)
    var spawnOpts = _.omit(opts, 'args');

    // Ensure we don't run concurrent cleans
    spawnOpts.preventConcurrentRuns = true;

    return processManager.spawnAnsiblePlay(ANSIBLE_DIR, 'hosts/localhost',
        'config-processor-clean.yml', opts.args, spawnOpts);
}

function runReadyDeployment(opts) {
    // Ensure opts are optional
    opts = opts || {};

    // Inherit spawnOpts from passed opts (except things handled locally)
    var spawnOpts = _.omit(opts, 'args');

    // Ensure we don't run concurrent ready-deployment
    spawnOpts.preventConcurrentRuns = true;

    var spawnPromise = processManager.spawnAnsiblePlay(ANSIBLE_DIR, 'hosts/localhost', 'ready-deployment.yml',
        opts.args, spawnOpts);

    spawnPromise.then(function() {
        spawnPromise.complete.then(function() {
            logger.debug('Ready Deploy completed successfully');
            currentInputModel.notifyClients();
        });
    });
    return spawnPromise;
}

/** Simple increment for generating unique vault-password filenames */
var vaultIndex = 0;
function getNextPasswordSuffix() {
    if (vaultIndex < Number.MAX_SAFE_INTEGER) {
        vaultIndex++;
    } else {
        vaultIndex = 0;
    }
    return vaultIndex;
}

function writeVaultPassword(encryptionKey) {
    var uniqVaultPassFile = vaultPasswordPath + '_' + getNextPasswordSuffix();
    return writeFileQ(uniqVaultPassFile, encryptionKey, {mode: 384}).then(function() {
        return uniqVaultPassFile;
    }).catch(function(error) {
        logger.error(error);
        throw error;
    });
}

function deleteVaultPassword(vaultFileName) {
    return unlinkQ(vaultFileName).catch(function(error) {
        logger.error(error);
        throw error;
    });
}

/**
 * Execute the 'site.yml' playbook, return the spawn promise for the play
 * @param {object=} opts collection of optional properties
 *        {string=} opts.encryptionKey configuration process encryption key
 *        {boolean=} opts.keepDayZero execute the playbook with '-e keep_dayzero=true'
 *        {boolean=} opts.destroyDayZeroOnSuccess after site successfully completes bring down the day zero installer by
 *        running the 'dayzero-stop.yml' playbook
 */
function runSite(opts) {
    opts = opts || {};

    opts.extraVars = opts.extraVars || {};
    if (opts.keepDayZero) {
        opts.extraVars['keep_dayzero'] = true;
        delete opts.keepDayZero;
    }
    var destroyDayZeroOnSuccess = opts.destroyDayZeroOnSuccess;
    if (destroyDayZeroOnSuccess) {
        delete opts.destroyDayZeroOnSuccess;
    }

    var sitePromise = startPlaybook('site.yml', opts);
    if (destroyDayZeroOnSuccess) {
        sitePromise.complete.then(function() {
            // Match legacy behaviour of waiting five minutes before taking down day zero installer
            setTimeout(function() {
                logger.info("Bringing down 'day zero' installer by playing 'dayzero-stop.yml'");
                startPlaybook('dayzero-stop.yml', {clientId: opts.clientId}).complete.catch(function() {
                    logger.error("Failed to bring down 'day zero' installer after successfully deploying");
                });
            }, 5 * 60 * 1000);
        });
    }

    return sitePromise;
}

/**
 * Start running a playbook returns a promise resolved when the process has spawned.
 * For convenience we also we forward the completion promise from the processManager
 * */
function startPlaybook(playbookFileName, opts) {

    opts = opts || {};
    opts.args = opts.args || [];
    opts.extraVars = opts.extraVars || {};

    var playbookDir = opts.playbookDir || SCRATCH_DIR;
    var inventoryFile = opts.inventoryFile;

    // Only set to default inventoryFile if missing from request
    if (_.isUndefined(inventoryFile)) {
        inventoryFile = 'hosts/verb_hosts';
    }

    // Ensure we don't kill ourselves while running a playbook
    if (isStandalone) {
        opts.extraVars['hux_svc_ignore_stop'] = true;
    }

    // Inherit spawnOpts from passed opts (except things handled locally)
    var spawnOpts = _.omit(opts, 'args');

    spawnOpts.preventConcurrentRuns = preventConcurrentRun(playbookFileName);

    // Write vault password to temporary file for ansible
    var vaultFileName;
    var vaultFilePromise;

    var encryptionKey = opts.encryptionKey;
    if (encryptionKey) {
        vaultFilePromise = writeVaultPassword(encryptionKey).then(function(uniqueVaultFileName) {
            vaultFileName = uniqueVaultFileName;
            opts.args.push('--vault-password-file');
            // N.B. we use basename to get a relative path which makes the dev case simpler
            opts.args.push(path.basename(uniqueVaultFileName));
        });
    } else {
        vaultFilePromise = true;
    }

    // Forward completion deferred from processManager to the returned promise
    var completionDeferred = Q.defer();
    var returnedPromise = Q.when(vaultFilePromise).then(function() {
        var spawnPromise = processManager.spawnAnsiblePlay(playbookDir, inventoryFile, playbookFileName,
            opts.args, spawnOpts);

        if (encryptionKey && vaultFileName) {
            spawnPromise.complete.finally(function() {
                deleteVaultPassword(vaultFileName);
            });
        }

        // Forward the state of the completion promise
        spawnPromise.complete.then(function(resolution) {
            completionDeferred.resolve(resolution);
        }, function(rejection) {
            completionDeferred.reject(rejection);
        });

        return spawnPromise;
    }).catch(function(error) {
        completionDeferred.reject(error);
        throw error;
    });

    returnedPromise.complete = completionDeferred.promise;
    return returnedPromise;
}

function handleAsyncSpawn(spawnPromise, response) {
    if (response) {
        spawnPromise.then(function(meta) {
            // Once the process has spawned, send the http response containing the pRef
            response.status(201).json(meta);
        }, function(error) {
            utils.sendErrorResponse(response, error, 'Failed to spawn ansible-playbook process');
        });
    }
    return spawnPromise;
}
