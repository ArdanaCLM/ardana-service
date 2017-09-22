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
var _ = require('lodash');
var fs = require('fs');
var Q = require('q');
var config = require('../../config');
var childProcess = require('child_process');
var exec = childProcess.exec;
var websocketServer = require('../../lib/websocket-server');
var mockery = require('mockery');
var logger = require('../../lib/logger');

mockery.enable();
/**
 * format of failPlaybook
 *  failPlaybook = {
 *    playbookName:{},
 *    playbookName:{args: ['nodelist="deployer"']}
 *  }
 */
var failPlaybook = {};

var processManagerMock = {
    spawnAnsiblePlay: function(dir, hostsFile, playbookName, arguments) {

        logger.info('Intercepted call to execute: ' +
            playbookName + ' with arguments: ' + arguments);

        var emptyPromise = Q();
        var failRun = false;
        if (_.has(failPlaybook, playbookName)) {
            if (_.has(failPlaybook[playbookName], 'args')) {

                var intersection = _.intersection(failPlaybook[playbookName].args, arguments);
                if (intersection.length != 0) {
                    logger.info('Failing playbook ' + playbookName + ' because of argument: ' + intersection);
                    failRun = true;
                }

            } else {
                failRun = true;
            }
        } else {
            logger.info('Wil succeed this run!');
        }

        emptyPromise.complete = failRun ? Q.reject('Failing run of ' +
            playbookName + ' with arguments: ' + arguments) : Q();
        return emptyPromise;
    }
};

mockery.registerMock('./process-manager', processManagerMock);

var osInstaller = require('../../lib/os-installer');

config.set('testing:mock', true);
config.set('testing:replaySpeed', 0.1);

var processManager = require('../../lib/process-manager');
processManager.init(config, websocketServer);
var osConfigData = JSON.parse(fs.readFileSync('test/data/osinstall_request.json'));

describe('osinstall tests', function() {

    osInstaller.setup();

    describe('tests with pre-image playbook failures', function() {

        it('should fail after a clean command failure', function(done) {

            failPlaybook['ready-install-os.yml'] = {};
            /** trigger OS installation **/
            osInstaller.install(config, osConfigData).catch(function() {
                var status = osInstaller.status();

                var serversAreErrorred = true;
                _.each(status.servers, function(serverState) {
                    serversAreErrorred = serversAreErrorred && (serverState === 'error');
                });

                failPlaybook = {};
                if (serversAreErrorred && status.hasError && status.finished) {
                    done();
                } else {
                    done('Failed with status: ' + JSON.stringify(status));
                }
            });
        });

        it('should fail after a power status command failure', function(done) {

            failPlaybook['bm-power-status.yml'] = {};
            /** trigger OS installation **/
            osInstaller.install(config, osConfigData).catch(function() {
                var status = osInstaller.status();
                var serversAreErrorred = true;
                _.each(status.servers, function(serverState) {
                    serversAreErrorred = serversAreErrorred && (serverState === 'pwr_error');
                });

                failPlaybook = {};

                if (serversAreErrorred && status.hasError && status.finished) {
                    done();
                } else {
                    done('Failed with status: ' + JSON.stringify(status));
                }
            });
        });

        it('should fail after a cobbler-deploy failure', function(done) {

            failPlaybook['cobbler-deploy.yml'] = {};
            /** trigger OS installation **/
            osInstaller.install(config, osConfigData).catch(function() {
                var status = osInstaller.status();
                var serversAreErrorred = true;
                _.each(status.servers, function(serverState) {
                    serversAreErrorred = serversAreErrorred && (serverState === 'error');
                });

                failPlaybook = {};
                if (serversAreErrorred && status.hasError && status.finished) {
                    done();
                } else {
                    done('Failed with status: ' + JSON.stringify(status));
                }
            });
        });

        it('should fail a subset of nodes', function(done) {

            failPlaybook['bm-reimage.yml'] = {
                args: ['nodelist="swpac1"',
                    'nodelist="swpac2"']
            };
            /** trigger OS installation **/
            osInstaller.install(config, osConfigData).catch(function() {
                var status = osInstaller.status();

                var testSucceeded = true;
                _.each(status.servers, function(serverState, key) {

                    if (serverState === 'error') {
                        if (key !== 'swpac1' && key !== 'swpac2') {
                            testSucceeded = false;
                        }
                        return;
                    }
                    testSucceeded = testSucceeded && (serverState === 'complete');
                });

                failPlaybook = {};
                if (testSucceeded && status.finished) {
                    /** explicity check is swpac1 & swpac2 were in error state **/
                    if (status.servers.swpac1 === 'error' && status.servers.swpac2 === 'error') {
                        return done();
                    }
                }
                done('Failed with status: ' + JSON.stringify(status));
            });
        });

        it('swpac1 should be removed from nodes after osconfig update', function(done) {

            failPlaybook['bm-reimage.yml'] = {
                args: ['nodelist="swpac2"']
            };

            /** remove swpac1 from the osConfigData **/
            var modOsConfigData = JSON.parse(JSON.stringify(osConfigData));
            var newServers = modOsConfigData.servers;
            newServers = newServers.slice(1);
            modOsConfigData.servers = newServers;
            /** trigger OS installation **/
            osInstaller.install(config, modOsConfigData).catch(function() {

                var status = osInstaller.status();

                var testSucceeded = true;
                _.each(status.servers, function(serverState, key) {

                    if (serverState === 'error') {
                        if (key !== 'swpac1' && key !== 'swpac2') {
                            testSucceeded = false;
                        }
                        return;
                    }
                    testSucceeded = testSucceeded && (serverState === 'complete');
                });

                failPlaybook = {};
                if (testSucceeded && status.finished) {
                    /** explicity check is swpac2 in error state & is swpac1 missing **/
                    if (status.servers.swpac2 === 'error' && !_.has(status.servers, 'swpac1')) {
                        return done();
                    }
                }
                done('Failed with status: ' + JSON.stringify(status));

            });
        });
    });

    describe('tests with no failures', function() {

        it('should say COMPLETED for all hosts', function(done) {

            /** trigger OS installation **/
            osInstaller.install(config, osConfigData).then(function() {
                /** periodically check for status **/
                var status = osInstaller.status();
                var serversAreReady = true;
                _.each(status.servers, function(serverState) {
                    serversAreReady = serversAreReady && (serverState === 'complete');
                });

                if (serversAreReady) {
                    done();
                }
            });
        });

        it('should never declare ready for any server, if all servers have the deployer IP', function(done) {

            var localIps;

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

            /** modify osConfig data **/
            var modOsConfigData = JSON.parse(JSON.stringify(osConfigData));

            /** trigger OS installation **/
            initLocalIps().then(function() {
                _.each(modOsConfigData.servers, function(server) {
                    server['ip-addr'] = localIps[0];
                });
                return osInstaller.install(config, modOsConfigData);
            }).then(function() {
                var status = osInstaller.status();
                /** if any servers has any other state than "complete", the test failed **/

                var serversAreComplete = true;
                _.each(status.servers, function(serverState) {
                    serversAreComplete = serversAreComplete && (serverState === 'complete');
                });
                done(!serversAreComplete);
            });
        });
    });
});


