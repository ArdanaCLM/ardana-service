/**
 * (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
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
var supertest = require('supertest');
var config = require('../../config');
var path = require('path');
var express = require('express');
var currentInputModel = require('../../lib/current-input-model');
var apiPath = config.get('apiEndpoint') + require('../../api/servers').getApiPath();
var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');

/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});


var app = require('../../index.js').express;

describe('Servers API Test', function() {

    it('GET should respond with json', function(done) {
        supertest(app).get(apiPath)
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });

    describe('Add new server', function() {
        /** TODO add server **/
        it('POST new server details should succeed', function(done) {
            supertest(app).post(apiPath)
                .send(serverDetails)
                .expect(200)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

        it('should add new server to the input model', function(done) {
            currentInputModel.getModel()
                .then(function() {
                    /** TODO check for servers **/
                    done();
                }).catch(function() {
                done('null');
            });
        });

        /** TODO add server **/
        it('POST invalid server details should fail', function(done) {
            supertest(app).post(apiPath)
                .send(serverDetails)
                .expect(500)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

    });

    describe('Update existing server', function() {
        /** TODO server details **/
        it('POST new server details should succeed', function(done) {
            supertest(app).put(apiPath)
                .send(serverDetails)
                .expect(200)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

        it('verify server was updated in the input model', function(done) {
            currentInputModel.getModel()
                .then(function() {
                    /** TODO check for servers **/
                    done();
                }).catch(function() {
                done('null');
            });
        });

        /** TODO add server **/
        it('POST invalid server details should fail', function(done) {
            supertest(app).post(apiPath)
                .send(serverDetails)
                .expect(500)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

    });


    describe('Delete server', function() {
        /** TODO server details **/
        it('DELETE new server details should succeed', function(done) {
            supertest(app).delete(apiPath)
                .expect(200)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

        it('verify server was deleted in the input model', function(done) {
            currentInputModel.getModel()
                .then(function() {
                    /** TODO check for servers **/
                    done();
                }).catch(function() {
                done('null');
            });
        });

        /** TODO add server **/
        it('DELETE invalid server details should fail', function(done) {
            supertest(app).post(apiPath)
                .send(serverDetails)
                .expect(500)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });

    });

    /**
     * TODO servers/process
     * TODO servers/:id/process
     */

});


