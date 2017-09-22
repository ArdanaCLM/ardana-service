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
var should = require('should');
var path = require('path');
var express = require('express');
var temp = require('temp');
var Q = require('q');
var fs = require('fs');

var config = require('../../config');
var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');
var deployerInCloudModel = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0',
                                     'ardana-ci', 'deployerincloud');
var ModelReader = require('../../lib/model-reader');
/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});


var currentInputModel = require('../../lib/current-input-model');
var knownControlPlane = 'control-plane-1';
var clusterName = 'testCluster';
var serverName = 'test';

describe('Current-Input-Model tests', function() {

    /**
     * Model operation tests.
     * Require access to a valid input model.
     * To run these tests, make sure the config.yml
     * override points to a valid ardana-input-model dir
     *
     */

    describe('Model', function() {

        config.override('paths:cloudDir', cloudDir);


        it('get success ', function(done) {

            currentInputModel.init(config);

            currentInputModel.getModel().then(function(model) {

                if (model) {
                    done();
                }
            }).catch(done);
        });

    });


    describe('Control Planes', function() {

        config.override('paths:cloudDir', cloudDir);
        config.override('paths:cloudModelPath', cloudDir);
        currentInputModel.init(config);


        it('get all ', function(done) {
            currentInputModel.getControlPlanes()
                .then(function(planes) {
                    /** check plane contents **/
                    done(!_.isArray(planes));
                }).catch(done);
        });

        it('get specific', function(done) {

            currentInputModel.getControlPlane(knownControlPlane)
                .then(function(controlPlane) {
                    done(!(controlPlane.name === knownControlPlane));
                }).catch(done);
        });

        it('get invalid plane', function(done) {

            currentInputModel.getControlPlane('foobarPlane')
                .then(function() {
                    done('not expected!');
                }).catch(_.partial(done, null));
        });
    });


    describe('Cluster', function() {

        var clusterData = {
            name: clusterName
        };

        function clusterExistsInModel(model, clusterName) {
            return _.find(model.inputModel['control-planes'][0].clusters, {name: clusterName});
        }

        it('add to plane ', function(done) {

            currentInputModel.addCluster(knownControlPlane, clusterData)
                .then(currentInputModel.getModel)
                .then(function(model) {
                    done(!clusterExistsInModel(model, clusterName));
                }).catch(done);
        });

        it('add to invalid plane', function(done) {

            currentInputModel.addCluster('fooBarCluster', clusterData)
                .then(currentInputModel.getModel)
                .then(function() {

                    /** should have errored out **/
                    done('should have failed!');
                }).catch(_.partial(done, null));
        });

        it('add null cluster to  plane', function(done) {

            currentInputModel.addCluster(knownControlPlane, null)
                .then(currentInputModel.getModel)
                .then(function() {

                    /** should have errored out **/
                    done('should have failed!');
                }, _.partial(done, null));
        });

    });


    describe('Servers', function() {

        /** minimum fields required to validate a server **/
        var serverData = {
            server: {
                id: 'test',
                'ip-addr': 'address',
                role: 'role'
            }
        };

        function modelHasServer(model, id) {
            return _.find(model.inputModel.servers, {id: id});
        }

        it('get all ', function(done) {

            currentInputModel.getServers()
                .then(function(servers) {

                    if (_.isArray(servers)) {
                        done();
                    }
                }).catch(function(err) {
                done(err);
            });
        });

        it('validate valid server', function(done) {
            currentInputModel.validateServer(serverData, true)
                .then(function() {
                    return done();
                }).catch(done);

        });

        it('validate invalid server', function(done) {
            /** invalidate serverData **/
            var serverData2 = JSON.parse(JSON.stringify(serverData));

            delete serverData2.server.id;
            currentInputModel.validateServer(serverData2, true)
                .then(function(valid) {
                    done('expected validation to fail');

                }, _.partial(done, null));

        });

        it('add new server', function(done) {

            currentInputModel.addServer(serverData)
                .then(currentInputModel.getModel)
                .then(function(model) {
                    return done(!modelHasServer(model, serverData.server.id));
                }).catch(done);
        });

        it('update existing server', function(done) {

            var serverData2 = JSON.parse(JSON.stringify(serverData));
            serverData2.server.role = 'role2';
            currentInputModel.updateServer(serverName, serverData2)
                .then(currentInputModel.getModel)
                .then(function(model) {
                    var modelServer = modelHasServer(model, serverData2.server.id);
                    return done(!(modelServer.role === serverData2.server.role));
                }).catch(done);
        });

        it('update invalid server', function(done) {

            currentInputModel.updateServer('foobarServer', serverData)
                .then(function() {
                    done('failed');
                }, _.partial(done, null));
        });

        it('delete valid server', function(done) {

            currentInputModel.getModel()
                .then(_.partial(currentInputModel.deleteServer, serverName))
                .then(currentInputModel.getModel)
                .then(function(model) {
                    return done(modelHasServer(model, serverName));
                }).catch(done);
        });

        it('delete invalid server', function(done) {

            currentInputModel.getModel()
                .then(_.partial(currentInputModel.deleteServer, 'foobarServer'))
                .then(function() {
                    done('failed');
                }, _.partial(done, null));
        });

        it('get all available servers', function(done) {

            currentInputModel.getModel()
                .then(currentInputModel.getAvailableServers)
                .then(function(servers) {
                    done(!_.isArray(servers));
                }).catch(done);
        });
    });

    describe('Git Operations', function() {


        it('get status ', function(done) {

            config.override('paths:ardanaDir', path.join(__dirname, '..', 'temp', 'openstack'));
            config.override('paths:cloudDir',
                path.join(__dirname, '..', 'temp', 'openstack', 'my_cloud',
                    'definition'));
            currentInputModel.init(config);
            currentInputModel.getStatus()
                .then(_.partial(done, null), done);
        });

        it('get state ', function(done) {

            currentInputModel.getState()
                .then(_.partial(done, null), done);
        });

        it('get history ', function(done) {

            currentInputModel.getHistory()
                .then(_.partial(done, null), done);
        });

        it('get site commit', function(done) {
            currentInputModel.getSiteCommit()
                .then(_.partial(done, null), done);
        });

        it('get current commit', function(done) {
            currentInputModel.getCurrentCommit()
                .then(_.partial(done, null), done);
        });

        it('get isBranchHead', function(done) {
            currentInputModel.isBranchHead()
                .then(_.partial(done, null), done);
        });

        it('get state with changes', function(done) {
            /** update input model and revert changes **/
            ModelReader.readTemplate(cloudDir)
                .then(currentInputModel.writeModel)
                .then(currentInputModel.getState)
                .then(function(data) {
                    if (data.name && data.name.indexOf('modified') == 0) {
                        return done();
                    }
                    done('Unexpected state: ' + JSON.stringify(data));
                })
                .catch(done);
        });

        it('clean state', function(done) {

            currentInputModel.clean()
                .then(currentInputModel.getState)
                .then(function(state) {

                    if (state.name === 'committed') {
                        return done();
                    }
                    done('Unexpected state: ' + JSON.stringify(state));
                })
                .catch(done);
        });

        it('change model and commit', function(done) {

            ModelReader.readTemplate(deployerInCloudModel)
                .then(currentInputModel.writeModel)
                .then(_.partial(currentInputModel.commit, 'test'))
                .then(currentInputModel.getState)
                .then(function(data) {
                    if (data.name === 'committed') {
                        return done();
                    }
                    done('Unexpected state: ' + JSON.stringify(data));
                })
                .catch(done);
        });


    });
});

