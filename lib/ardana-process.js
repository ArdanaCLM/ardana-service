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
var Q = require('q');

var logger = require('./logger');
var playbooksAPI = require('../api/playbooks');
var modelAPI = require('../api/model');
var utils = require('./utils');
var CONSTANTS = require('./constants');
var currentInputModel = require('./current-input-model');

var deployProcessExecuting;
var logPrepend = 'DEPLOY-PROCESS progress. ';

// Container for information/actions for each step in the process
var processSteps = {
    commit: {
        stage: 0,
        error: CONSTANTS.ERROR_CODES.PROCESS_COMMIT,
        verb: 'Committing Changes',
        execute: function(opts) {
            return currentInputModel.commit(opts.commitMessage);
        }
    },
    runConfig: {
        stage: 1,
        error: CONSTANTS.ERROR_CODES.PROCESS_VALIDATE,
        verb: 'Running Config Processor',
        execute: function(opts) {
            return playbooksAPI.runPlaybook('config-processor-run',
                _.pick(opts, ['encryptionKey', 'removeDeletedServers', 'freeUnusedAddresses', 'clientId'])).complete;
        }
    },
    ready: {
        stage: 2,
        error: CONSTANTS.ERROR_CODES.PROCESS_READY_DEPLOYMENT,
        verb: 'Readying for deployment',
        execute: function(opts) {
            return playbooksAPI.runPlaybook('ready-deployment', _.pick(opts, ['clientId'])).complete;
        }
    },
    limit: {
        stage: 3,
        verb: 'Fetching host name to --limit',
        execute: function(opts) {
            if (!opts.limitToId) {
                logger.info('No server id supplied, skipping --limit');
                return;
            }
            return currentInputModel.getCPOutputEntity('server_info_yml')
                .then(function(servers) {
                    var server = servers.parsedEntity[opts.limitToId];
                    if (server) {
                        opts.limit = server.hostname;
                    } else {
                        logger.error('Failed to find server with id \'' + opts.limitToId + '\'. Deploy will ' +
                            'be called but will not be limited to this single server.');
                    }
                });
        }
    },
    deploy: {
        stage: 4,
        error: CONSTANTS.ERROR_CODES.PROCESS_DEPLOY,
        verb: 'Deploying',
        execute: function(opts) {
            var sitePromise = playbooksAPI.runPlaybook('site', _.pick(opts, ['limit', 'clientId', 'encryptionKey']));

            sitePromise.then(function(meta) {
                opts.response.status(201).json(meta);
            }).catch(function(error) {
                error.code = processSteps.deploy.error.code;
                utils.sendErrorResponse(opts.response, error);
            });

            return sitePromise.complete;
        }
    },
    genHostsFile: {
        stage: 5,
        error: CONSTANTS.ERROR_CODES.PROCESS_GEN_HOSTS_FILE,
        verb: 'Generating hosts file',
        execute: function(opts) {
            var opts = _.pick(opts, ['clientId', 'encryptionKey']);
            opts.args = ['--tags', 'generate_hosts_file'];
            return playbooksAPI.runPlaybook('site', opts).complete;
        }
    },
    monascaCheck: {
        stage: 6,
        error: CONSTANTS.ERROR_CODES.PROCESS_MONASCA_CHECK,
        verb: 'Monasca ping',
        execute: function(opts) {
            var opts = _.pick(opts, ['clientId', 'encryptionKey']);
            opts.args = ['--tags', 'active_ping_checks'];
            return playbooksAPI.runPlaybook('monasca-deploy', opts).complete;
        }
    }
};

/**
 * Create and execute the deploy chain
 * @param {object} step - Stage to reach. Must be entry from {@link #processSteps}
 * @param {object} processOpts Set of properties required by steps
 * @returns {object} Contains a promise and the current executing step
 */
function _deployProcess(step, processOpts) {
    var chain = { };

    function _executeStep(step) {
        return function() {
            logger.info(logPrepend + 'Step: ' + step.verb);
            chain.step = step;
            return step.execute(processOpts);
        }
    }

    chain.promise = Q();
    // Build up promise chain
    var pos = 0;
    while (pos <= step.stage) {
        var currentStep = _.find(processSteps, { stage: pos++});
        chain.promise = chain.promise.then(_executeStep(currentStep));
    }

    // Return the chain object which contains the promise and the 'step' at which the promise is on. The promise
    // represents all steps including possibly deploy
    return chain;
}

/**
 * Run through the deploy process (commit, config processor, ready deployment, deploy).
 * @param {object} request - Express request object used for associated http request
 * @param {object} response - Express response object used for associated http response. A response is sent once deploy
 * successfully STARTS.
 * @param {object} appConfig - application configuration
 * @param {object} step - Stage to reach. Must be entry from {@link #processSteps}
 * @param {object} options - Collection of options for function
 * {object} options.modelBeforeChange - Model to revert to if there are failures at ANY point in the process
 * {boolean} options.deploy - If truthy will attempt to deploy. If false will do all steps up to deploy
 * @returns {object} A promise object which completes once process exits
 */
function deployProcess(request, response, appConfig, step, options) {

    //Step 1) Block concurrent calls to just this method
    //TODO: Step 2) Block concurrent calls to all OPS console request
    //TODO: Step 3) Global block? Block out any write/commit/ready/deploy step
    if (deployProcessExecuting) {
        // This will cover the case when call 'A' has made it to deploying and the response has been returned, call 'B'
        // then makes a request, passes through the parent and into here.
        utils.sendErrorResponse(response, {
            isUserError: 'Cannot run through concurrent deploy processes',
            code: CONSTANTS.ERROR_CODES.PROCESS_CONCURRENT.code
        });
        return Q.reject('Cannot run through concurrent deploy processes');
    }

    deployProcessExecuting = true;
    logger.info(logPrepend + 'Started');

    // Collection process options
    var processOpts = {
        appConfig: appConfig,
        commitMessage: _.get(request, 'body.process.commitMessage') || 'ardana-service deploy process',
        encryptionKey: _.get(request, 'body.process.encryptionKey', ''),
        clientId: request.headers.clientid,
        removeDeletedServers: _.get(request, 'body.removeDeletedServers'),
        freeUnusedAddresses: _.get(request, 'body.freeUnusedAddresses'),
        limit: _.get(request, 'body.process.limit'),
        limitToId: _.get(request, 'body.process.limitToId', ''),
        response: response
    };

    var initialValidationStage = {
        verb: 'Unknown process stage to run to',
        stage: -1,
        error: {}
    };

    var chain;
    if (!step) {
        chain = {
            step: initialValidationStage,
            promise: Q.reject('No deploy step specified to run to')
        };
    } else if (!_.find(processSteps, step)) {
        chain = {
            step: initialValidationStage,
            promise: Q.reject('No deploy step specified to run to')
        };
    } else {
        // Execute process
        chain = _deployProcess(step, processOpts);
    }


    return chain.promise
        .catch(function(error) {
            // Handle ANY error that occurred in the process
            var failureMessage = "Failed to run through part of full deploy process\nFailed at step: '" +
                chain.step.verb + "'";

            // Is step before the 'site' playbook? Ensure we respond to the http request
            if (chain.step.stage < processSteps.deploy.stage) {

                error = error || {};

                // Format the error object into one required by sendErrorResponse
                if (_.isString(error)) {
                    error = {
                        detail: error
                    };
                } else if (error.code) {
                    error.orig_code = error.code;
                }
                // Determine if this is a config-processor-run invalidate error
                if (chain.step === processSteps.runConfig && error.pRef && error.code !== 0) {
                    error.code = CONSTANTS.ERROR_CODES.PROCESS_VALIDATE_INVALID.code;
                    error.isUserError = 'Invalid configuration';
                } else {
                    error.code = chain.step.error.code;
                }

                // Also handles logging
                utils.sendErrorResponse(response, error, failureMessage);
            } else {
                // No need to send a response, just handle logging
                logger.error(logPrepend + failureMessage, error);
            }

            if (options.modelBeforeChange) {
                // Attempt to roll back state (git and scratch folders)
                logger.info(logPrepend + 'Resetting state (git and scratch folders)');
                var rollBackChain = {
                    promise: true
                };

                // Ensure ~/ardana files are correct
                return modelAPI.writeModel(options.modelBeforeChange)
                    .then(function() {
                        // The process error'd while at 'chain.step'. Try to roll back to stage just before
                        var rollbackToStep = _.find(processSteps, { stage: chain.step.stage - 1 });

                        if (rollbackToStep.stage > processSteps.ready.stage) {
                            rollbackToStep = processSteps.ready;
                        }

                        if (rollbackToStep) {
                            var rollbackCommitMsg = 'Roll back of state by ardana-service. Original commit ...' +
                                "\n'" + processOpts.commitMessage + "'.\nReason for roll back: " + failureMessage;

                            var rollbackProcessOpts = _.clone(processOpts);
                            rollbackProcessOpts.removeDeletedServers = true;
                            rollbackProcessOpts.commitMessage = rollbackCommitMsg;
                            rollbackProcessOpts.limitToId = undefined;
                            rollBackChain = _deployProcess(rollbackToStep, rollbackProcessOpts);
                            rollBackChain.promise.catch(function(error) {
                                throw {
                                    message: 'Roll back of state by ardana-service failed. Original commit ...' +
                                    "\n'" + processOpts.commitMessage + "'\nFailed at step: " + rollBackChain.step.verb,
                                    error: error
                                };
                            });
                        }

                        return rollBackChain.promise;
                    })
                    .then(function() {
                        logger.info(logPrepend + 'Resetting state (git and scratch folders) succeeded');
                    })
                    .catch(function(error) {
                        logger.error(logPrepend + 'Resetting state (git and scratch folders) failed. ', error);
                    })
                    .finally(function() {
                        // Return a failed promise only when we've tidied up the previous change
                        throw error;
                    });
            }

            // Return a failed promise only when we've tidied up the previous change
            throw error;
        })
        .finally(function() {
            logger.info(logPrepend + 'Finished');
            deployProcessExecuting = false;
        });
}

exports.deployProcess = deployProcess;
exports.processSteps = processSteps;
