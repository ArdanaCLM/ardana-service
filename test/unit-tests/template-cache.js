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
var templateCache = require('../../lib/template-cache.js');
var cloudDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'ardana-ci', 'mid-size');

/**
 * Disable keystone
 */
config.override('keystone_config', {disabled: true});


var templatesDir = path.join(__dirname, '..', 'temp', 'ardana-input-model', '2.0', 'examples');
config.override('paths:templatesDir', templatesDir);

describe('Template cache tests', function() {

    describe('templates are in specific format', function() {

        config.override('paths:cloudDir', cloudDir);

        it('success ', function(done) {
            templateCache.init(config).then(function() {
                done(templateCache.templates.length === 0 ? 'templates are null' : false);
            }, done);
        });
    });

});

