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

exports.readTemplate = readTemplate;
exports.getIdKey = getIdKey;

//////////

var constants = require('./constants');
var path = require('path');
var fs = require('fs');
var yaml = require('js-yaml');
var _ = require('lodash');
var Q = require('q');

var readFileQ = Q.denodeify(fs.readFile);
var readdirQ = Q.denodeify(fs.readdir);
var statQ = Q.denodeify(fs.stat);

var INPUT_MODEL = constants.INPUT_MODEL;
var PASS_THROUGH = 'pass-through';

function readFolder(template, dir) {

    function processFile(filePath) {

        var tFilePath = path.join(dir, filePath);
        return statQ(tFilePath).then(function(fileMetadata) {
            // Recurse down directories
            if (fileMetadata.isDirectory()) {
                return readFolder(template, tFilePath);
            }
            // Skip the cloudConfig file as we will have already read it
            if (filePath !== constants.CLOUD_CONFIG && path.extname(filePath) === constants.YML_EXT) {
                //console.log('Loading: ' + tFilePath);
                return readFileQ(tFilePath, constants.UTF8)
                    .then(function(yamlString) {
                        var tsDoc = yaml.safeLoad(yamlString, {json: true});
                        _.forEach(_.keys(tsDoc), function(key) {
                            var val = tsDoc[key];
                            if (_.isArray(val)) {
                                if (_.has(template[INPUT_MODEL], key)) {
                                    // We need to break the reference by cloning
                                    // template[INPUT_MODEL][key] = template[INPUT_MODEL][key].concat(val);
                                    template[INPUT_MODEL][key].push.apply(template[INPUT_MODEL][key], val);
                                } else {
                                    // template[INPUT_MODEL][key] = val;
                                    template[INPUT_MODEL][key] = _.clone(val, true);
                                }
                            } else {
                                if (_.has(template[INPUT_MODEL], key)) {
                                    // Deep merge objects into a new Object
                                    // template[INPUT_MODEL][key] = _.merge({}, template[INPUT_MODEL][key], val);
                                    _.merge(template[INPUT_MODEL][key], val);
                                } else {
                                    // template[INPUT_MODEL][key] = val;
                                    template[INPUT_MODEL][key] = _.clone(val, true);
                                }
                            }
                        });
                        //template[INPUT_MODEL] = _.defaults(template[INPUT_MODEL], tsDoc);
                        return tsDoc;
                    })
                    .then(_.partial(addFile, template, tFilePath))
                    .catch(function(e) {
                        template.errors.push('Failed to load file: ' + tFilePath + ': ' + e);
                    });
            } else if (filePath.match(constants.README)) {
                var ext = path.extname(filePath).replace('\.', '');
                return readFileQ(tFilePath, constants.UTF8).then(
                    function(content) {
                        template.readme[ext] = content;
                    });
            }
        });
    }

    return readdirQ(dir).then(function(files) {
        var promises = [];
        _.each(files, function(filePath) {
            promises.push(processFile(filePath));
        });
        return Q.all(promises);
    });
}


// Update fileSectionMaps for files that contain object-section
function trackObjects(template) {

    // identify if objects are split across files
    _.each(template.fileInfo._object_data, function(sectionFiles, sectionName) {
        if (sectionFiles.length > 1) {

            if (sectionName !== PASS_THROUGH) {

                var errMessage = 'Non pass-through object section ' + sectionName + ' has been found in the' +
                    ' multiple files in the mode. This is not currently supported!';
                try {
                    errMessage += ' Files are: ' +
                        JSON.stringify(_.map(sectionFiles, function(sectionFile) {
                            return _.keys(sectionFile)[0];
                        }));
                } catch (ignored) {
                }

                throw errMessage;
            }
            // object occurs in several files
            _.each(sectionFiles, function(fileSectionData) {
                // element is format {fileName: sectionData}
                var fileName = Object.keys(fileSectionData)[0];
                var propertyKeys = getPropertyPaths(fileSectionData[fileName]);
                var keyStruct = {};
                keyStruct.type = 'object';
                keyStruct[sectionName] = propertyKeys;
                template.fileInfo.fileSectionMap[fileName].push(keyStruct);
            });
        } else {

            var fileName = Object.keys(sectionFiles[0])[0];
            template.fileInfo.fileSectionMap[fileName].push(sectionName);
        }
    });
}

function readTemplate(dir) {

    var configFile = path.join(dir, constants.CLOUD_CONFIG);

    // Read the contents of the file

    var template = {
        name: null,
        version: null,
        readme: null,
        fileInfo: {},
        errors: []
    };
    template[INPUT_MODEL] = {};

    return readFileQ(configFile, constants.UTF8).then(function(yamlString) {
        var doc = yaml.safeLoad(yamlString, {json: true});

        if (!doc) {
            throw 'Cloud config file is empty';
        }

        // Check the version number
        if (!doc.product || doc.product.version !== constants.VERSION) {
            // Wrong version number
            throw 'Unexpected cloud config product version';
        }

        if (!doc.cloud || !doc.cloud.name) {
            // Wrong version number
            throw 'Cloud config error: no name specified';
        }

        // Store the cloud product metadata
        //template.metadata = doc;
        template.version = doc.product.version;
        template[INPUT_MODEL].cloud = doc.cloud;
        template.name = doc.cloud.name;
        template.readme = {};
        // Used to record which files were loaded and what was loaded from each file
        template.fileInfo.configFile = configFile;
        template.fileInfo.directory = dir;

        return addFile(template, configFile, doc).then(function() {
            // Load all of the files from the directory

            // There is no data directory any longer - all files in any subdirectory will be read
            return readFolder(template, dir).then(function() {

                // Add tracking data for objects if required
                trackObjects(template);
                delete template.fileInfo._object_data;
                return template;

            });
        });

    });
}

/**
 * Three kinds of ids are used in input model
 * 'id' is used for servers
 * 'region-name' is used for swift/rings.yml
 * 'name' is used for everything else
 * 'node_name' is used by baremetalConfig.yml
 */
function getIdKey(obj) {
    if (!obj) {
        return null;
    }
    if (obj.hasOwnProperty('name')) {
        return 'name';
    }
    if (obj.hasOwnProperty('id')) {
        return 'id';
    }
    if (obj.hasOwnProperty('region-name')) {
        return 'region-name';
    }
    if (obj.hasOwnProperty('node_name')) {
        return 'node_name';
    }
    return null;
}

/**
 * Record each file that is read including which sections (top-level keys) are in each file
 * @param {Object} template Current Template object
 * @param {String} filePath Path of the file that is being currently added to the Template object
 * @param {JSON} json   The JSON content of the file
 */
function addFile(template, filePath, json) {
    //logger.debug('Called addFile(' + filePath + ')');
    if (!template.fileInfo.files) {
        template.fileInfo.files = [];
        template.fileInfo.sections = {};
        template.fileInfo.fileSectionMap = {};
        template.fileInfo.mtime = -1;
        /* Object-based sections are tracked
         * internally in this structure.
         * Properties contained in objects that
         * are split across files are updated
         * after the entire model has been read in.
         */
        template.fileInfo._object_data = {};
    }

    // Use a relative file path when recording files
    var relativeFilePath = filePath;
    if (relativeFilePath.indexOf(template.fileInfo.directory) === 0) {
        relativeFilePath = relativeFilePath.substr(template.fileInfo.directory.length + 1);
    }

    template.fileInfo.files.push(relativeFilePath);

    // Get the last modified time for the file and update the overall modified time if it is earlier
    return statQ(filePath).then(function(stats) {
        var mtime = stats.mtime.getTime();
        if (mtime > template.fileInfo.mtime) {
            template.fileInfo.mtime = mtime;
        }

        if (!json) return;

        var fileSectionMap = [];
        template.fileInfo.fileSectionMap[relativeFilePath] = fileSectionMap;

        _.each(json, function(sectionData, sectionName) {
            if (!_.has(template.fileInfo.sections, sectionName)) {
                template.fileInfo.sections[sectionName] = [];
            }
            template.fileInfo.sections[sectionName].push(relativeFilePath);

            if (_.isArray(sectionData) && sectionData.length > 0) {
                // Store key information
                var keyStruct = {};
                keyStruct[sectionName] = [];
                keyStruct.keyField = getIdKey(sectionData[0]);
                _.each(sectionData, function(element) {
                    keyStruct[sectionName].push(element[keyStruct.keyField]);
                });
                fileSectionMap.push(keyStruct);
                /* new property to distinguish between
                 * "array'ed" sections and
                 * objects that are split across file */
                keyStruct.type = 'array';

            } else if (_.isPlainObject(sectionData) && sectionName !== 'product') {
                // keep track of sections that are objects
                if (!_.has(template.fileInfo._object_data, sectionName)) {
                    template.fileInfo._object_data[sectionName] = [];
                }
                var obj = {};
                obj[relativeFilePath] = sectionData;
                template.fileInfo._object_data[sectionName].push(obj);

            } else {
                // Catches empty arrays, primitives
                fileSectionMap.push(sectionName);
            }

        });
    });

}


/**
 * Get paths of nested properties as an array.
 * Don't recurse more than 2 levels deeper
 * @param {Object} obj Object
 * @param {string} stack partial path
 * @param {bool} dontRecurse stop recursion level
 * @returns {Array}  Properties array
 */
function getPropertyPaths(obj, stack, dontRecurse) {
    var paths = [];
    _.each(_.keys(obj), function(key) {
        if (_.isPlainObject(obj[key]) && !dontRecurse) {
            var newPath = stack ? stack + '.' + key : key;
            paths.push.apply(paths, getPropertyPaths(obj[key], newPath, true));
        } else {
            paths.push(stack ? stack + '.' + key : key);
        }
    });
    return paths;
}

