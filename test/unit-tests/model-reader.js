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
var ModelReader = require('../../lib/model-reader');
var path = require('path');

var midSizeExamplePath = path.join(__dirname, '..', 'temp', 'ardana-input-model',
    '2.0', 'examples', 'entry-scale-esx-kvm-vsa');

describe('Model Reader tests', function() {


    describe('Read valid model', function() {

        it(' success ', function(done) {
            ModelReader.readTemplate(midSizeExamplePath)
                .then(function(model) {
                    if (_.isObject(model) &&
                        model.fileInfo &&
                        model.inputModel &&
                        model.errors.length === 0) {
                        return done();
                    }
                    done('model is invalid');
                }, done);
        });

    });

    describe('Read invalid model', function() {

        it('success ', function(done) {
            ModelReader.readTemplate('/tmp/foo')
                .then(function(model) {
                    done('should have failed');
                }, _.partial(done, null));
        });

    });

});

