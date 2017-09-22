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
var config = require('../../config');
var path = require('path');
var reader = require('../../lib/model-reader');
var Writer = require('../../lib/model-writer');
var constants = require('../../lib/constants');
var exec = require('child_process').exec;
var fs = require('fs');
var mkdirp = require('mkdirp');
var temp = require('temp');
var Q = require('q');
var yaml = require('js-yaml');

var modelWriter = new Writer(config);
var midSizeExamplePath = path.join(__dirname, '..', 'temp', 'ardana-input-model',
    '2.0', 'examples', 'entry-scale-esx-kvm-vsa');

/*
 * These tests all four cases when writing an input model. The cases are:
 *
 * 1. Input model contains no new additions, therefore fileInfo is correct.
 *
 * 2. Input model contains additions to a section (i.e. new servers have been added).
 * If the section is maintained in a single file,
 * all elements of that section will be appended to that file
 *
 * 3. Input model contains additions to a section (i.e. disk model in mid-scale)
 * that has been split into several files. If the section has been split in a fashion where
 * each file contains exactly one element, then each new element added will be written to its own file.
 *
 * 4. Input model contains additions to a section that is split over several files, however
 * some files have  more elements than others. In this case, we will write all new elements of the section
 * to a new file.
 */

var mkdirQ = Q.denodeify(temp.mkdir);
var INPUT_MODEL = 'inputModel';
var modelWriterPrefix = 'model_writer';

/**
 * "lassThroughMode" Single object based section present in multiple files
 */
function writeOutPassthroughFiles(lassThroughMode) {

    var computePassthrough = {
        product: {
            version: 2
        },
        'pass-through': {
            global: {
                'install-env': 'legacy',
                'thirdparty-folder': '/home/stack/stage/thirdparty',
                'test': {
                    'test2': 1
                }
            }
        }
    };

    var neutronPassthrough = {
        product: {
            version: 2
        },
        'pass-through': {
            global: {
                'esx_cloud2': true
            }
        }
    };

    if (lassThroughMode) {
        computePassthrough['lass-through'] = computePassthrough['pass-through'];
        delete computePassthrough['pass-through'];
        neutronPassthrough = computePassthrough;
    }

    fs.writeFileSync(path.join(midSizeExamplePath, 'data', 'passthrough_compute.yml'),
        yaml.safeDump(computePassthrough));
    fs.writeFileSync(path.join(midSizeExamplePath, 'data', 'passthrough_neutron.yml'),
        yaml.safeDump(neutronPassthrough));
}


function deletePassthroughFiles() {
    fs.unlink(path.join(midSizeExamplePath, 'data', 'passthrough_compute.yml'));
    fs.unlink(path.join(midSizeExamplePath, 'data', 'passthrough_neutron.yml'));
}

describe('Model writer tests', function() {

    // var Q = require('q');
    // var FulfilledPromise = function() {
    //     var deferred = Q.defer();
    //     deferred.resolve();
    //     return deferred.promise;
    // };
    // var RejectedPromise = function() {
    //     var deferred = Q.defer();
    //     deferred.reject(new Error());
    //     return deferred.promise;
    // };
    // describe("RejectedPromise#", function() {
    //     it('is promise', function() {
    //         return RejectedPromise().should.be.a.Promise();
    //     });
    //     it('is fulfilled', function() {
    //         return RejectedPromise().should.be.fulfilled();
    //     });
    //     it('should not be fulfilled', function() {
    //         return RejectedPromise().should.not.be.fulfilled();
    //     });
    //     it('should be rejected', function() {
    //         return RejectedPromise().should.be.rejected();
    //     });
    //     it('should not be rejected', function() {
    //         return RejectedPromise().should.not.be.rejected();
    //     });
    // });
    // describe("FulfilledPromise#", function() {
    //     it('is promise', function() {
    //         return FulfilledPromise().should.be.a.Promise();
    //     });
    //     it('is fulfilled', function() {
    //         return FulfilledPromise().should.be.fulfilled();
    //     });
    //     it('should not be fulfilled', function() {
    //         return FulfilledPromise().should.not.be.fulfilled();
    //     });
    //     it('should be rejected', function() {
    //         return FulfilledPromise().should.be.rejected();
    //     });
    //     it('should not be rejected', function() {
    //         return FulfilledPromise().should.not.be.rejected();
    //     });
    // });


    it('should write out template with no changes', function(done) {
        // Normal case, no changes to template
        mkdirQ(modelWriterPrefix + '_normal').then(function(dirPath) {
            // Normal case, no changes to template
            console.log('Wrote normal model to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(_.partialRight(writeTemplate, dirPath));
        }).then(_.partial(done, null)).catch(done);
    });

    it('should write out template with 5 added servers', function(done) {
        mkdirQ(modelWriterPrefix + '_added_servers').then(function(dirPath) {
            // Added 5 more servers to the template. All servers should be added to the servers.yml file
            console.log('Wrote model with 5 more servers to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(model) {
                    // Add 5 more servers **/
                    for (i = 0; i < 5; i++) {
                        var serverClone = _.clone(_.last(model.inputModel.servers));
                        serverClone.id = 'server-' + i;
                        model[INPUT_MODEL].servers.push(serverClone);
                    }
                    return writeTemplate(model, dirPath)
                        .then(_.partial(reader.readTemplate, dirPath))
                        .then(function(newModel) {
                            // test if servers section is distributed over three files now
                            var onlyOneServersFile =
                                newModel.fileInfo.sections.servers.length === 1;
                            if (!onlyOneServersFile) {
                                throw 'Template was written incorrectly!';
                            }
                        });
                });
        }).then(_.partial(done, null)).catch(done);
    });

    it('should write out template with 5 added disk models', function(done) {
        mkdirQ(modelWriterPrefix + '_diskmodels').then(function(dirPath) {
            // Added 5 more disk models. Five more disk models files should be created
            console.log('Wrote model with 5 more disk models to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(model) {
                    for (i = 0; i < 5; i++) {
                        var modelClone = _.clone(_.last(model[INPUT_MODEL]['disk-models']));
                        modelClone.name = 'model-' + i;
                        model[INPUT_MODEL]['disk-models'].push(modelClone);
                    }
                    return writeTemplate(model, dirPath)
                        .then(_.partial(reader.readTemplate, dirPath))
                        .then(function(newModel) {
                            // Test if servers section is distributed over three files now
                            var diskModelFilesExist =
                                newModel.fileInfo.sections['disk-models'].length === 10;
                            if (!diskModelFilesExist) {
                                throw 'Template was written incorrectly!';
                            }
                        });
                });
        }).then(_.partial(done, null)).catch(done);
    });

    it('should write out template with 5 more servers across three files', function(done) {
        mkdirQ(modelWriterPrefix + '_more_servers').then(function(dirPath) {
            // Added 5 more servers, but input model contains two server files. Should create a third one
            console.log('Wrote model with 5 more servers, but 2 servers files to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(model) {
                    // amend fileInfo
                    var modelfileSectionServers = model.fileInfo.fileSectionMap['data/servers.yml'];

                    var serversFileClone = JSON.parse(JSON.stringify(modelfileSectionServers));

                    // deleting baremetal
                    serversFileClone.length--;

                    // remove last two servers
                    // first three servers
                    var index = -1;
                    _.each(modelfileSectionServers, function(section, ind) {
                        if (_.isObject(section)) {
                            index = ind;
                        }
                    });
                    modelfileSectionServers[index].servers = modelfileSectionServers[index].servers.splice(0, 3);
                    serversFileClone[index].servers = serversFileClone[index].servers.splice(3);
                    model.fileInfo.fileSectionMap['data/servers2.yml'] = serversFileClone;
                    // patch sections file
                    model.fileInfo.sections.servers.push('data/servers2.yml');

                    for (i = 0; i < 5; i++) {
                        var serverClone = _.clone(_.last(model[INPUT_MODEL].servers));
                        serverClone.id = 'server-' + i;
                        model[INPUT_MODEL].servers.push(serverClone);
                    }
                    return writeTemplate(model, dirPath)
                        .then(_.partial(reader.readTemplate, dirPath))
                        .then(function(newModel) {
                            // Test if servers section is distributed over three files now
                            var newServerFileExists = newModel.fileInfo.sections.servers.length === 3;
                            if (!newServerFileExists) {
                                throw 'Template was written incorrectly!';
                            }
                        });
                });
        }).then(_.partial(done, null)).catch(done);
    });

    it('should write out template with a new section', function(done) {
        mkdirQ(modelWriterPrefix + '_new_section').then(function(dirPath) {
            // Added nic-mappings. Should create a new file dedicated to it
            console.log('Added nic-mappings. Should create ' +
                'a new file dedicated to it! Writing to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                // Nuke nic-mappings from fileInfo
                delete model.fileInfo.fileSectionMap['data/nic_mappings.yml'];
                delete model.fileInfo.sections['nic-mappings'];


                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {
                        /* make sure that a nic-mapping file was written,
                         * with a nic-mapping section */
                        var nicMappingSectionExists = _.has(newModel, 'fileInfo.sections.nic-mappings');
                        if (!nicMappingSectionExists) {
                            throw 'Template was written incorrectly!';
                        }
                    });
            });

        }).then(_.partial(done, null)).catch(done);
    });

    it('should write pass-through data properly', function(done) {
        mkdirQ(modelWriterPrefix + '_passthrough').then(function(dirPath) {

            // Write pass-through files to midSize model
            writeOutPassthroughFiles();
            // Added nic-mappings. Should create a new file dedicated to it
            console.log('Added two pass-through files. Should re-create ' +
                'these two files! Writing to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {

                        deletePassThroughFiles();
                        // Validate pass-through files contain the correct data
                        var computeData = _.find(newModel.fileInfo.fileSectionMap['data/passthrough_compute.yml'],
                            function(section) {
                                return _.isObject(section);
                            })['pass-through'];
                        var expectedComputeData = ['global.install-env',
                            'global.thirdparty-folder', 'global.test'];
                        var neutronData = _.find(newModel.fileInfo.fileSectionMap['data/passthrough_neutron.yml'],
                            function(section) {
                                return _.isObject(section);
                            })['pass-through'];
                        var expectedNeutronData = ['global.esx_cloud2'];

                        if (!(_.isEqual(expectedNeutronData.sort(), neutronData.sort()) &&
                            _.isEqual(expectedComputeData.sort(), computeData.sort()))) {
                            throw 'Model was written incorrectly!';
                        }

                    });
            });

        }).then(_.partial(done, null)).catch(done);
    });

    it('should be able to write new pass-through', function(done) {
        mkdirQ(modelWriterPrefix + '_passhtrough').then(function(dirPath) {

            var PASS_THROUGH = 'pass-through';
            // Write pass-through files to midSize model
            writeOutPassthroughFiles();
            // Added nic-mappings. Should create a new file dedicated to it
            console.log('Added two pass-through files. Should re-create ' +
                'these two files! Writing to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                // add additional properties in pass-through
                model[INPUT_MODEL][PASS_THROUGH]['servers2'] = ['random', 'data'];
                model[INPUT_MODEL][PASS_THROUGH].global.foo = 'bar';

                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {

                        deletePassThroughFiles();
                        // check new passthrough file exists
                        var newPassThroughFile = _.find(newModel.fileInfo.fileSectionMap, function(fileData, fileName) {
                            return fileName.indexOf('data/pass_through_') === 0;
                        });

                        var actualData = _.find(newPassThroughFile, function(sectionDetails) {
                            return _.isObject(sectionDetails);
                        })[PASS_THROUGH];
                        var expectedData = ['global.foo', 'servers2'];

                        should(newModel.fileInfo.sections['pass-through'].length).equal(4);
                        should(_.isEqual(expectedData.sort(), actualData.sort())).is.true();
                    });
            });

        }).then(_.partial(done, null)).catch(done);
    });
    it('should be able to delete a passthrough file', function(done) {
        mkdirQ(modelWriterPrefix + '_passhtrough').then(function(dirPath) {

            var PASS_THROUGH = 'pass-through';
            // write pass-through files to midSize model
            writeOutPassthroughFiles();
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                deletePassThroughFiles();
                // add additional properties in pass-through
                delete model[INPUT_MODEL][PASS_THROUGH].global.esx_cloud2;

                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {

                        // check new passthrough file exists

                        var neutronPassThrough = _.find(newModel.fileInfo.fileSectionMap, function(fileData, fileName) {
                            return fileName.indexOf('data/passthrough_neutron') === 0;
                        });

                        deletePassThroughFiles();
                        should(neutronPassThrough).be.undefined();
                    });
            });

        }).then(_.partial(done, null)).catch(done);
    });

    it('should be able to write a new section', function(done) {
        mkdirQ(modelWriterPrefix + '_obj').then(function(dirPath) {

            writeOutPassthroughFiles();
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                // write pass-through files to midSize model
                model[INPUT_MODEL]['MY_SECTION'] = {'foo': 'bar'};

                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {

                        deletePassThroughFiles();
                        should.exist(newModel.fileInfo.sections['MY_SECTION']);
                    });
            });

        }).then(_.partial(done, null)).catch(done);
    });

    it('should be able to write two objects in "non-split" mode', function(done) {
        mkdirQ(modelWriterPrefix + '_obj').then(function(dirPath) {

            writeOutPassthroughFiles(true);
            return reader.readTemplate(midSizeExamplePath).then(function(model) {

                return writeTemplate(model, dirPath)
                    .then(_.partial(reader.readTemplate, dirPath))
                    .then(function(newModel) {
                        should(newModel.fileInfo.sections['lass-through'].length).equal(2);
                    });
            });

        }).should.be.rejected().then(_.partial(done, null));
    });


    function deletePassThroughFiles() {

        var computeFile = path.join(midSizeExamplePath, 'data', 'passthrough_compute.yml');
        var neutronFile = path.join(midSizeExamplePath, 'data', 'passthrough_neutron.yml');
        if (fs.existsSync(computeFile)) {
            fs.unlinkSync(computeFile);
        }
        if (fs.existsSync(neutronFile)) {
            fs.unlinkSync(neutronFile);
        }
    }

    after(function(done) {
        deletePassThroughFiles();
        exec('rm -rf /tmp/' + modelWriterPrefix + '*', done);
    });

});


function writeTemplate(inputModel, path) {
    return modelWriter.writeModel(Object.assign({}, inputModel), path)
        .catch(function(err) {
            console.log('Failed to write file due to: ' + err);
        });
}
