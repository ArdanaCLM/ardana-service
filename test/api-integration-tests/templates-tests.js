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

var apiPath = config.get('apiEndpoint') + require('../../api/templates').getApiPath();
var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');

/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});

var templateName = 'templateName';

var app = require('../../index.js').express;

describe('Templates API Test', function() {

    it('GET should respond with json', function(done) {
        supertest(app).get(apiPath)
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });
    it('GET specific template', function(done) {
        supertest(app).get(apiPath + '/' + templateName)
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });
    it('GET specific template graph', function(done) {
        supertest(app).post(apiPath + '/' + templateName + '/graph')
            .expect(200)
            .expect('Content-Type', /json/)
            .end(function(err, res) {
                done(err);
            });
    });
});


