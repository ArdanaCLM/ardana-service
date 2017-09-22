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

var child_process = require('child_process');
var yaml = require('js-yaml');
var fs = require('fs');
var _ = require('lodash');
var logger = require('./logger');
var Q = require('q');
var path = require('path');
var constants = require('./constants');
var utils = require('./utils');

var statQ = Q.denodeify(fs.stat);
var renameQ = Q.denodeify(fs.rename);
var unlinkQ = Q.denodeify(fs.unlink);

var RECORD_META_EXT = '.yml';
var RECORD_LOG_EXT = '.log';

// Metadata about running processes (before this is persisted to FS)
var processMetadata = {};

var webSocketServer = null;

var config;
var remoteDeployer, remoteUser = 'stack', sshPort = '22';

/** Prevent spawning of new processes flag **/
var preventNewProcesses = false;

var logsDir, archiveDir, maxLogSize;
var archiveInProgress = false;

function makeLogMessage(pRef, data, stream) {
    return JSON.stringify({
        type: webSocketServer.MESSAGE_TYPES.LOG_DATA,
        pRef: pRef,
        data: data,
        stream: stream
    });
}

function makeProcessEndMessage(meta) {
    return JSON.stringify({
        type: webSocketServer.MESSAGE_TYPES.PROCESS_END,
        meta: makeCleanMeta(meta)
    });
}

function makeProcessStartMessage(meta) {
    return JSON.stringify({
        type: webSocketServer.MESSAGE_TYPES.PROCESS_START,
        meta: makeCleanMeta(meta)
    });
}

function ackSend(error) {
    if (error) {
        logger.error('Failed to send message via the WebSocket: ', error);
    }
}

function makeLogHandler(meta, stream) {
    return function(data) {
        var dataString = data.toString();
        meta.log += dataString;

        if (meta.streamingClients.length > 0) {
            var message = makeLogMessage(meta.pRef, dataString, stream);
            for (var i = 0; i < meta.streamingClients.length; i++) {
                var ws = webSocketServer.webSocketClients[meta.streamingClients[i]];
                ws.send(message, ackSend);
            }
        }
    }
}

// When a client disconnects, clean up
function removeClient(connectionId) {
    for (var pRef in processMetadata) {
        if (processMetadata.hasOwnProperty(pRef)) {
            var meta = processMetadata[pRef];
            if (meta.alive) {
                for (var i = meta.streamingClients.length - 1; i >= 0; i--) {
                    var aConnectionId = meta.streamingClients[i];
                    if (aConnectionId === connectionId) {
                        meta.streamingClients.splice(i, 1);
                    }
                }
            }
        }
    }
    delete webSocketServer.webSocketClients[connectionId];
}

function getLogFilePath(pRef) {
    return listPersistedPlays().then(function(records) {
        for (var i = 0; i < records.length; i++) {
            var recordBase = records[i];
            if (utils.endsWith(recordBase, pRef.toString())) {
                return getLogFile(recordBase);
            }
        }
        // If we reach here, we looped through all records and didn't match the supplied pRef
        throw {
            message: 'Cannot find record for process reference supplied: ' + pRef,
            statusCode: 404
        };
    });
}

function getMeta(pRef, cleanMeta) {
    if (!pRef) {
        return Q.reject('Cannot get meta for invalid process reference supplied: ' + pRef);
    }
    var meta = processMetadata[pRef];
    if (meta) { // Process still alive or being persisted
        logger.debug('Found meta in memory for live process:', pRef);
        if (cleanMeta) {
            // Clean out any property that may be locked
            meta = makeCleanMeta(meta);
        }
        return Q(meta);
    }

    // Check if we have a record of a past process matching this pRef
    return listPersistedPlays().then(function(records) {

        for (var i = 0; i < records.length; i++) {
            var recordBase = records[i];

            if (utils.endsWith(recordBase, pRef.toString())) {
                // Found it! Read both meta and log in parallel
                logger.debug('Found meta on filesystem for terminated process:', recordBase);

                // Read and parse meta file
                var parsedMetaPromise = Q.nfcall(fs.readFile, getMetaFile(recordBase), 'utf8').then(function(rawMeta) {
                    meta = yaml.safeLoad(rawMeta);
                    return meta;
                });

                var errorHandler = function(error) {
                    // Oops, something went terribly wrong either reading or parsing...
                    var errorMessage = 'Failed loading record of terminated process from filesystem';
                    logger.error(errorMessage, error);
                    throw errorMessage;
                };

                if (cleanMeta) {
                    // Don't bother reading the log file if clean meta was requested
                    return parsedMetaPromise.catch(errorHandler);
                }

                // Read log file
                var logPromise = Q.nfcall(fs.readFile, getLogFile(recordBase), 'utf8');

                // Return a join on both promises
                return Q.all([parsedMetaPromise, logPromise]).spread(function(meta, log) {
                    meta.log = log;
                    return meta;
                }).catch(errorHandler);
            }
        }
        // If we reach here, we looped through all records and didn't match the supplied pRef
        throw {
            message: 'Cannot find meta for process reference supplied: ' + pRef,
            statusCode: 404
        };
    });
}

/** Truncate the beginning of the passed log if its size exceeds maxSize */
function sliceLog(log, maxSize) {
    if (maxSize && log.length > maxSize) {
        logger.info('Log larger than requested max size ' + maxSize + ' bytes, will slice off the beginning');
        var index = log.lastIndexOf('\n', log.length - maxSize);
        if (index === -1) {
            logger.warn('Failed to find suitable slice point... Sending full log');
            return log;
        }
        return log.slice(index);
    }
    return log;
}

/** Send log of a process to a WebSocket client */
function sendLog(pRef, clientId, maxSize) {
    var webSocketClient = webSocketServer.webSocketClients[clientId];
    getMeta(pRef).then(function(meta) {
        if (meta.log) {
            logger.info('Found log for: ' + pRef);
            var log = sliceLog(meta.log, maxSize);
            webSocketClient.send(makeLogMessage(pRef, log, 'logFile'), ackSend);
        }

        // Register client for future messages if process still lives
        if (meta.alive) {
            // Check if client is not yet registered
            if (meta.streamingClients.indexOf(clientId) === -1) {
                logger.debug('Registered new client for live log stream on: ', pRef);
                meta.streamingClients.push(clientId);
            }
        } else {
            logger.debug('Notifying client that process [' + pRef + '] has in fact already ended');
            // Instantly notify client that the process has in fact ended
            webSocketClient.send(makeProcessEndMessage(meta), ackSend);
        }
    }, function(error) {
        logger.warn(error);
    });
}

function getMetaFile(recordBase) {
    return path.join(logsDir, recordBase + RECORD_META_EXT);
}

function getLogFile(recordBase) {
    return path.join(logsDir, recordBase + RECORD_LOG_EXT);
}

/** Persist the metadata and log of an Ansible play to the filesystem */
function persistPlayLog(pRef) {
    var meta = processMetadata[pRef];

    // Split metadata and log to keep meta records small
    var logString = meta.log;
    delete meta.log;

    // Skip undefined
    var yamlString = yaml.safeDump(meta, {skipInvalid: true});

    // Put log back into the meta object
    meta.log = logString;

    logger.debug('Persisting process record to local filesystem...');

    var recordBasename = path.join(logsDir, pRef);
    var recordMeta = recordBasename + RECORD_META_EXT;
    var recordLog = recordBasename + RECORD_LOG_EXT;
    fs.writeFile(recordLog, logString, function(error) {
        if (error) {
            // Shouldn't really happen unless we run out of disk space
            logger.error('Failed to save process log to file system: ' + recordLog, error);
            delete processMetadata[pRef];
        } else {
            fs.writeFile(recordMeta, yamlString, function(error) {
                if (error) {
                    // Shouldn't really happen unless we run out of disk space
                    logger.error('Failed to save process record to file system: ' + recordMeta, error);
                } else {
                    logger.debug('Successfully persisted process record: ' + recordMeta);
                    archivePlays();
                }
                delete processMetadata[pRef];
            });
        }
    });
}

/** Return a promise which will be resolved with the list of basenames for all persisted plays */
function listPersistedPlays() {
    return Q.nfcall(fs.readdir, logsDir).then(function(files) {
        var yamlFiles = files.filter(function(file) {
            return utils.endsWith(file, RECORD_META_EXT);
        });
        // Return base name of each play
        return _.map(yamlFiles.reverse(), function(fileName) {
            return fileName.slice(0, -RECORD_META_EXT.length);
        });
    });
}

/** Move the meta for passed plays into the archive directory and delete the associated log */
function archiveLogs(toArchive) {
    var promises = [];
    _.forEach(toArchive, function(baseName) {
        var metaName = baseName + RECORD_META_EXT;
        var logName = baseName + RECORD_LOG_EXT;
        var renamePromise = renameQ(path.join(logsDir, metaName), path.join(archiveDir, metaName));
        var deletePromise = unlinkQ(path.join(logsDir, logName));
        promises.push(Q.all([renamePromise, deletePromise]).then(function() {
            logger.debug('Archive logs: successfully archived process record: ' + baseName);
        }));
    });
    return Q.all(promises).then(function() {
        logger.debug('Archive logs: finished archiving old process records');
    });
}

/** Conveniently, our records filenames begin with the startTime for the process.
 * This allows efficient sorting and filtering of records */
function getStartTimeFromName(fileName) {
    // N.B. pRef = <startTime>_<pid>
    var underscoreIndex = fileName.indexOf('_');
    if (underscoreIndex < 1) {
        throw 'Invalid record name ' + fileName + ' not following the <startTime>_<pid> pattern';
    }
    var startTimeMs = parseInt(fileName.slice(0, underscoreIndex), 10);
    if (isNaN(startTimeMs)) {
        throw 'Invalid record name ' + fileName + ' not following the <startTime>_<pid> pattern';
    }
    return startTimeMs;
}

/** Archive older plays so that the total log size is under the configured threshold
 * Return a promise resolved with the number of bytes reclaimed by the archive operation */
function archivePlays() {

    // Prevent concurrent archiving
    if (archiveInProgress || preventNewProcesses) {
        logger.debug('Archive logs: archiving already in progress or shutting down.');
        return Q.resolve(0);
    }

    archiveInProgress = true;
    logger.debug('Archive logs: calculating current logs size...');
    return Q.nfcall(fs.readdir, logsDir).then(function(files) {

        var logFiles = files.filter(function(file) {
            return utils.endsWith(file, RECORD_LOG_EXT);
        });

        // Map of log name to byte size
        var fileToSize = {};
        var totalSize = 0;
        var promiseForStats = [];
        _.forEach(logFiles, function(logFile) {
            promiseForStats.push(statQ(path.join(logsDir, logFile)).then(function(stat) {
                // Record the size as we go
                fileToSize[logFile] = stat.size;
                totalSize += stat.size;
                return stat;
            }));
        });

        return Q.all(promiseForStats).then(function() {
            if (totalSize > maxLogSize) {
                // Need to archive logs
                logger.debug('Archive logs: current logs size: ' + totalSize + 'B is above threshold: ' + maxLogSize +
                    'B, archiving...');

                // Extract startTime from each filename and sort oldest first
                try {
                    logFiles.sort(function(file1, file2) {
                        var startTime1 = getStartTimeFromName(file1);
                        var startTime2 = getStartTimeFromName(file2);
                        return startTime1 - startTime2;
                    });
                } catch (error) {
                    // If we're unable to sort by time, we cannot archive safely
                    logger.error(error + ', refusing to archive');
                    return 0;
                }

                var toArchive = [];
                var excessBytes = totalSize - maxLogSize;
                var bytesSaved = 0;
                var index = 0;
                while (excessBytes >= 0) {
                    var logFile = logFiles[index++];
                    excessBytes -= fileToSize[logFile];
                    bytesSaved += fileToSize[logFile];
                    toArchive.push(logFile.slice(0, -RECORD_LOG_EXT.length));
                }
                return archiveLogs(toArchive).then(function() {
                    return bytesSaved;
                });
            }
            logger.debug('Archive logs: current logs size: ' + totalSize + 'B is under threshold: ' + maxLogSize +
                'B, no need to archive.');
            return 0;
        });

    }).finally(function() {
        archiveInProgress = false;
    });
}

/** Set of properties that should not be auto serialised for process events */
var liveProperties = [
    'process',
    'streamingClients',
    'log'
];

function createNewProcessMeta(pRef, pid, startTime, commandString, child, clientId) {
    return {
        // Serialised properties
        pRef: pRef,
        pid: pid,
        startTime: startTime,
        endTime: undefined,
        code: undefined,
        commandString: commandString,
        killed: false,
        alive: true,
        clientId: clientId,

        // Non serialised properties
        log: '',
        process: child,
        streamingClients: []
    };
}

// Public functions

function init(conf, wsServer) {
    config = conf;

    logsDir = config.get('logsDir');
    archiveDir = config.get('archiveDir');
    maxLogSize = config.get('archiveThresholdMb') * 1024 * 1024;
    if (isNaN(maxLogSize)) {
        throw 'Bad configuration: archiveThresholdMb not a valid number: ' + config.get('archiveThresholdMb');
    }
    remoteDeployer = config.get('deployer:remote');
    sshPort = config.get('deployer:sshPort') || '22';
    if (remoteDeployer) {
        logger.info('Working against remote deployer [' + remoteDeployer + ':' + sshPort + ']');
    }

    var messageHandler = function(message, clientId) {
        sendLog(message.pRef, clientId, message.maxSize);
    };

    wsServer.addActionHandler('getLog', messageHandler);
    wsServer.addClientDisconnectHandler(removeClient);
    webSocketServer = wsServer;

    // Initialise record directories
    if (!fs.existsSync(logsDir)) {
        logger.debug('Created empty ' + logsDir + ' directory for persisting process records');
        fs.mkdirSync(logsDir);
    }

    if (!fs.existsSync(archiveDir)) {
        logger.debug('Created empty ' + archiveDir + ' directory for archiving process records');
        fs.mkdirSync(archiveDir);
    }

    archivePlays();

}

function kill(pRef) {
    // Check we have a matching process currently running
    if (!processMetadata[pRef]) {
        logger.warn('Client attempted to kill non-existing process: ' + pRef);
        throw {
            message: 'No such process, PID: ' + pRef,
            statusCode: 404
        };
    }

    logger.info('Attempting to kill child process...');
    var meta = processMetadata[pRef];
    meta.process.kill('SIGINT');
    meta.killed = true;
}

function getLog(pRef, maxSize) {
    return getMeta(pRef).then(function(meta) {
        return sliceLog(meta.log, maxSize);
    });
}

function makeCleanMeta(meta) {
    return _.omit(meta, liveProperties); // shallow clone
}

function getPlays(options) {

    var opts = options || {};

    var now, maxAgeMs, maxNumber;
    var timeThreshold;

    if (opts.maxAge) {
        maxAgeMs = parseInt(opts.maxAge, 10) * 1000;
        if (isNaN(maxAgeMs)) {
            return Q.reject({
                isUserError: "maxAge value '" + opts.maxAge + "' is not a valid integer"
            });
        }
        now = Date.now();
        timeThreshold = now - maxAgeMs;
    }

    if (opts.maxNumber) {
        maxNumber = parseInt(opts.maxNumber, 10);
        if (isNaN(maxNumber) || maxNumber < 1) {
            return Q.reject({
                isUserError: "maxNumber value '" + opts.maxNumber + "' is not a positive integer"
            });
        }
    }

    var promiseForPlays;

    var needOnlyLive, needOnlyArchived;
    if (!utils.hasParam(opts, 'live')) { // If 'live' is missing, list all plays
        needOnlyLive = needOnlyArchived = false;
    } else {
        try {
            needOnlyLive = utils.parseBoolParam(opts, 'live');
        } catch (error) {
            return Q.reject(error);
        }
        needOnlyArchived = !needOnlyLive;
    }
    if (needOnlyLive) {
        var livePlays = {};
        _.forEach(processMetadata, function(meta, pRef) {
            livePlays[pRef] = makeCleanMeta(meta);
        });
        promiseForPlays = Q(livePlays);
    } else {
        // We definitely need archived plays
        promiseForPlays = listPersistedPlays().then(function(records) {
            var oldPlays = {};
            for (var i = 0; i < records.length; i++) {
                var recordBase = records[i];
                // Sync is ok as meta files are tiny
                var rawMeta = fs.readFileSync(getMetaFile(recordBase), 'utf8');
                oldPlays[recordBase] = yaml.safeLoad(rawMeta);
            }

            if (needOnlyArchived) {
                return oldPlays;
            }

            // Need all, merge live and old plays (this copes with partly written records)
            var allPlays = {};
            // TODO: use _.assignWith when moving to lodash 4.x
            _.assign(allPlays, processMetadata, oldPlays, function(objectValue, sourceValue) {
                return makeCleanMeta(sourceValue);
            });

            return allPlays;
        });
    }

    return promiseForPlays.then(function(plays) {

        // Sort plays: most recently started first
        var sortedPlays = _.values(plays);
        sortedPlays.sort(function(meta1, meta2) {
            return meta2.startTime - meta1.startTime;
        });

        // Filter out old plays if required
        if (maxAgeMs) {
            var filtered = [];
            for (var j = 0; j < sortedPlays.length; j++) {
                var meta = sortedPlays[j];
                if (meta.startTime < timeThreshold) {
                    break;
                }
                filtered.push(meta);
            }
            sortedPlays = filtered;
        }

        // Filter out excess plays if required
        if (maxNumber && sortedPlays.length > maxNumber) {
            sortedPlays = sortedPlays.slice(0, maxNumber);
        }

        return sortedPlays;
    });

}

// Replace the value of passed param by stars
function _obfuscateParam(string, param) {
    var regex = new RegExp('("' + param + '":")([^"]*)"', 'gi');
    return string.replace(regex, function(match, key, value) {
        var stars = new Array(value.length + 1).join('*');
        return key + stars + '"';
    });
}

/**
 * Asynchronously spawn a process on the local machine.
 * Note: 2 Promises are involved:
 *     - the spawn promise is resolved when we have spawned the async process
 *     - the complete promise is resolved when the process has finished
 * The completion promise is attached to the returned promise as .complete
 * Both promises will be rejected if spawning fails
 * The completion promise will be rejected if the process exits with non-zero status
 * @param {string} cwd directory in which the command will run
 * @param {string} command the command to run
 * @param {Array} args the arguments passed to the command
 * @param {Object=} opts additional options described below
 *            {Object=} opts.env environment the command will run in
 *            {string=} opts.description human readable description of the command
 *            {boolean=} opts.internal do not report the process via getPlays() and do not persist its log
 *            {boolean=} opts.preventConcurrentRuns prevent spawning another instance of the same playbook
 *            {string=} opts.clientId a string to identify the creator of the process
 * */
function spawnProcess(cwd, command, args, opts) {
    logger.debug('Attempting to spawn child process...');

    // Ensure options are optional...
    opts = opts || {};

    // Used when rejecting various promises
    var reason;

    // Create our two deferred objects
    var spawnDeferred = Q.defer();
    var completionDeferred = Q.defer();

    // Attach the completion promise to the spawn promise
    spawnDeferred.promise.complete = completionDeferred.promise;

    // Attach completion debug log callbacks
    completionDeferred.promise.then(function(meta) {
        logger.info('Process ' + meta.pRef + ' completed successfully');
        return meta;
    }, function(meta) {
        var msg = 'Process ' + meta.pRef + ' exited with non zero code: ' + meta.code;
        logger.info(msg);
        throw meta;
    });

    if (preventNewProcesses) {
        reason = {
            log: 'Prevented spawning of process because the service is shutting down.',
            code: constants.ERROR_CODES.SHUTTING_DOWN.code,
            statusCode: 403
        };
        spawnDeferred.reject(reason);
        completionDeferred.reject(reason);
        return spawnDeferred.promise;
    }

    var pRef; // Our own unique process reference
    var pid; // The real OS process ID (PID)
    var child;
    var commandString;

    commandString = opts.description || command + ' ' + args.join(' ');

    // Obfuscate encryption key and rekey here so it's not saved in clear text on the filesystem
    commandString = _obfuscateParam(commandString, 'encrypt');
    commandString = _obfuscateParam(commandString, 'rekey');

    var spawnOptions = {cwd: cwd};
    if (opts.env) {
        spawnOptions.env = opts.env;
    }

    if (opts.preventConcurrentRuns) {
        /** scan processMetadata to find another playbook instance
         *  TODO: BRUI-191 for taking ansible arguments into account
         */
        for (var aPRef in processMetadata) {
            if (!processMetadata.hasOwnProperty(aPRef)) { continue; }
            var aMeta = processMetadata[aPRef];
            if (aMeta.alive && aMeta.commandString.indexOf(commandString) > -1) {
                reason = {
                    commandString: commandString,
                    log: 'Failed to spawn child process: another instance of this playbook is already running',
                    code: constants.ERROR_CODES.CONCURRENT_PROCESS_RUNNING.code,
                    statusCode: 403
                };
                spawnDeferred.reject(reason);
                completionDeferred.reject(reason);
                return spawnDeferred.promise;
            }
        }
    }

    child = child_process.spawn(command, args, spawnOptions);
    child.on('error', function(error) {
        if (!pid) {
            logger.error('Failed to spawn child process', error);
            var reason = {
                commandString: commandString,
                log: 'Failed to spawn child process: ' + error,
                code: 127
            };
            spawnDeferred.reject(reason);
            completionDeferred.reject(reason);
        } else {
            // The process could not be killed or sending a message to the child process failed for whatever reason
            logger.error('Process could not be killed or we failed to send a message', error);
        }
    });

    pid = child.pid;
    if (!pid) { // PID is created synchronously
        // NO PID abort - we'll reject both promises in the error handler
        return spawnDeferred.promise;
    }

    // Make sure our process references don't collide in case of PID reuse
    var startTime = Date.now();
    pRef = startTime.toString() + '_' + pid.toString();

    logger.info('Successfully spawned child process with PID:' + pid + ' pRef: ' + pRef);

    var meta = createNewProcessMeta(pRef, pid, startTime, commandString, child, opts.clientId);
    if (!opts.internal) {
        processMetadata[pRef] = meta;
    }

    child.stdout.on('data', makeLogHandler(meta, 'stdout'));
    child.stderr.on('data', makeLogHandler(meta, 'stderr'));

    child.on('close', function(code) {
        // Mark process as terminated
        meta.endTime = Date.now();
        meta.code = code;
        meta.logSize = meta.log.length;
        delete meta.process;
        delete meta.alive;
        delete meta.streamingClients;

        // Notify all active clients about the process end
        if (!opts.internal) {
            var message = makeProcessEndMessage(meta);
            for (var clientId in webSocketServer.webSocketClients) {
                if (!webSocketServer.webSocketClients.hasOwnProperty(clientId)) {
                    continue;
                }
                var ws = webSocketServer.webSocketClients[clientId];
                ws.send(message, ackSend);
            }
        }

        completionDeferred[code === 0 ? 'resolve' : 'reject'](makeCleanMeta(meta));
        if (!opts.internal) {
            persistPlayLog(pRef);
        }
    });

    if (!opts.internal) {
        // Notify all active clients about the new process
        var message = makeProcessStartMessage(meta);
        for (var clientId in webSocketServer.webSocketClients) {
            if (!webSocketServer.webSocketClients.hasOwnProperty(clientId)) {
                continue;
            }
            var ws = webSocketServer.webSocketClients[clientId];
            ws.send(message, ackSend);
        }
    }

    spawnDeferred.resolve(makeCleanMeta(meta));
    return spawnDeferred.promise;
}

function addArg(args, argKey, argValue) {
    if (_.isUndefined(argValue)) {
        return;
    }
    args.push(argKey);

    // When run via SSH, the argument needs to be quoted
    args.push(remoteDeployer ? "'" + argValue + "'" : argValue);
}

function addExtraVars(args, extraVars) {
    if (extraVars && Object.keys(extraVars).length > 0) {
        addArg(args, '--extra-vars', JSON.stringify(extraVars));
    }
}

/**
 * Asynchronously spawn an ansible playbook. The playbook will either be run locally or on a remote deployer (requires
 * config string 'deployer:remote'. If config boolean 'testing:mock' is true and the playbook exists in config array
 * 'testing:mockPlaybooks' the run will be 'mocked' instead.
 * @param {string} cwd directory in which the command will run. This should be a relative path to home (remote deployer
 * will ssh into home, local deployment will join path to home).
 * @param {string} inventoryFile the path to ansible's inventory file
 * @param {string} playbook the playbook to run
 * @param {Array} args the arguments passed to the command
 * @param {Object=} opts additional options described below
 *          {string=} opts.clientId a string to identify the creator of the process
 *          {boolean=} opts.preventConcurrentRuns prevent spawning another instance of the same process/playbook
 *          {boolean=} opts.noColor - disable colors in ansible logs
 *          {Object=} opts.extraVars JSON value for the '--extra-vars' playbook argument
 *          {string=} opts.limit value for the '--limit' playbook argument
 *          {string=} opts.tags value for the '--tags' playbook argument
 *          {string=} opts.skipTags value for the '--skip-tags' playbook argument
 * */
function spawnAnsiblePlay(cwd, inventoryFile, playbook, args, opts) {

    var command;
    var ansibleArgs;
    var env;

    // Ensure opts are optional
    opts = opts || {};
    args = args || [];

    addExtraVars(args, opts.extraVars);
    addArg(args, '--limit', opts.limit);
    addArg(args, '--tags', opts.tags);
    addArg(args, '--skip-tags', opts.skipTags);

    // FIXME: better encapsulation of test/mock code please, this is way too interleaved with prod code
    if (remoteDeployer) { // Via SSH
        command = 'ssh';

        // In remote case when passed cwd is absolute, make relative to homePath
        if (path.isAbsolute(cwd)) {
            cwd = path.relative(config.get('homePath'), cwd);
        }

        var ansibleCommand = 'ansible-playbook ';
        if (inventoryFile) {
            ansibleCommand += '-i ' + inventoryFile + ' ';
        }
        ansibleCommand += playbook;
        if (args.length > 0) {
            ansibleCommand += ' ' + args.join(' ');
        }
        ansibleArgs = [remoteUser + '@' + remoteDeployer];
        if (sshPort !== '22') {
            ansibleArgs.push('-p ' + sshPort);
        }

        var bashCommand = '';
        if (!opts.noColor) {
            bashCommand += 'export ANSIBLE_FORCE_COLOR=true; ';
        }
        bashCommand += 'export PYTHONUNBUFFERED=1; ';
        bashCommand += 'cd ' + cwd + ' && ' + ansibleCommand;

        ansibleArgs.push(bashCommand);

        env = {};
        cwd = ''; // Local cwd becomes irrelevant in the remote case (we cd in the ssh session)

    } else { // Run directly on machine
        command = 'ansible-playbook';
        ansibleArgs = [];
        if (inventoryFile) {
            ansibleArgs.push('-i');
            ansibleArgs.push(inventoryFile);
        }
        ansibleArgs.push(playbook);

        // If a relative path was passed in, it means relative to homePath
        if (!path.isAbsolute(cwd)) {
            cwd = path.join(config.get('homePath'), cwd);
        }

        // FIXME: better encapsulation of test/mock code please, this is way too interleaved with prod code
        // Check for mock mode
        if (config.isMocked() && _.indexOf(config.get('testing:mockPlaybooks'), playbook) >= 0) {
            command = 'nodejs';
            ansibleArgs.unshift(__dirname + '/../../' + config.get('testing:mockAnsibleScript'));
            // Local cwd is irrelevant in the mocked case (nodejs should be on path)
            cwd = '';
        }

        ansibleArgs.push.apply(ansibleArgs, args);
        env = _.clone(process.env);
        if (!opts.noColor) {
            env['ANSIBLE_FORCE_COLOR'] = true;
        }
        env['PYTHONUNBUFFERED'] = 1;
    }

    return spawnProcess(cwd, command, ansibleArgs, {
        env: env,
        preventConcurrentRuns: opts.preventConcurrentRuns,
        clientId: opts.clientId
    });
}

// The following are used when shutting down the service

/** Check if processes are running **/
function areProcessesRunning() {
    return _.keys(processMetadata).length > 0;
}

/** Prevent spawning of any new processes **/
function preventSpawn() {
    preventNewProcesses = true;
}

// Public API
module.exports.kill = kill;
module.exports.getPlays = getPlays;
module.exports.spawnAnsiblePlay = spawnAnsiblePlay;
module.exports.spawnProcess = spawnProcess;
module.exports.getLog = getLog;
module.exports.getLogFilePath = getLogFilePath;
module.exports.getMeta = getMeta;
module.exports.init = init;

// The following are used by the ardana-service shutdown hook
module.exports.areProcessesRunning = areProcessesRunning;
module.exports.preventSpawn = preventSpawn;
