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
var supertest = require('supertest');
var config = require('../../config');
var path = require('path');
var express = require('express');

var modelPath = config.get('apiEndpoint') + require('../../api/model').getApiPath();
var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');

/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});


var app = require('../../index.js').express;

describe('Model API Test', function() {

    it('GET should return JSON', function(done) {
        supertest(app).get(modelPath)
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });


    it('GET should return 500 when model doesn\'t exist', function(done) {
        /** TODO change cloudDirPath **/
        supertest(app).get(modelPath)
            .expect(500)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });


    //it('POST', function(done) {
    //    /** TODO read template and post **/
    //    supertest(app).post(modelPath)
    //        .send(newModel)
    //        .expect(200)
    //        .expect('Content-Type', /json/)
    //        .end(function(err, res) {
    //            done(err);
    //        });
    //});

    it('Commit new model', function(done) {
        /** TODO get message **/
        supertest(app).post(modelPath + '/commit')
            .send('test')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });

    it('GET commit history for model', function(done) {
        /** TODO get message **/
        supertest(app).get(modelPath + '/history')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });

    it('GET model state', function(done) {
        /** TODO get message **/
        supertest(app).get(modelPath + '/state')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });

    it('GET unstaged changes', function(done) {
        /** TODO cause changes in the git repo **/
        supertest(app).get(modelPath + '/changes')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });

    it('DELETE all unstaged changes', function(done) {
        /** TODO cause changes in the git repo **/
        supertest(app).delete(modelPath + '/changes')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                /** TODO verify that it did somethign **/
                done(err);
            });
    });


});

