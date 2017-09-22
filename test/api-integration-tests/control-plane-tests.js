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

var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');
var apiPath = config.get('apiEndpoint') + require('../../api/control-plane').getApiPath();

/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});


var app = require('../../index.js').express;

describe('Control Plane API Test', function() {


    describe('GET tests', function() {
        it('should fail with 500 if no model is found, content should be json', function(done) {
            supertest(app).get(apiPath)
                .expect(500)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    done(err);
                });
        });


        it('should return 200 with a valid input model', function(done) {

            var initialCloudDir = config.get('paths:cloudDir');
            config.override('paths:cloudDir', cloudDir);
            var app = require('../../index.js').express;
            supertest(app).get(apiPath)
                .expect(200)
                .expect('Content-Type', /json/)
                .end(function(err, res) {
                    console.log(res.body);
                    done(err);

                });
        });
    });


});

