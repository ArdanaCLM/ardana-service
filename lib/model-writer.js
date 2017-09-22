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

var constants = require('./constants');
var path = require('path');
var fs = require('fs');
var yaml = require('js-yaml');
var _ = require('lodash');
var Q = require('q');
var logger = require('./logger');
var walk = require('fs-walk');
var mkdirp = require('mkdirp');
var uuid = require('uuid');

var INPUT_MODEL = constants.INPUT_MODEL;
var PASS_THROUGH = 'pass-through';
var writeFileQ = Q.denodeify(fs.writeFile);

function ModelWriter(config) {
    _.bindAll.apply(_, [this].concat(_.functions(ModelWriter.prototype)));
    this.inputModelPath = config.get('paths:cloudDir');
}

function deleteValue(keysToDelete, keyField, obj) {
    var foundObj = false;
    _.forEach(keysToDelete, function(key) {
        if (obj[keyField] === key) {
            foundObj = true;
        }
    });
    return foundObj;
}

/** Fetch all sections that still
 * contain elements that have not
 * been written to any file **/
function extractLeftOverSections(inputModel) {
    var sectionsWithNewContent = [];
    _.forEach(inputModel[INPUT_MODEL], function(sectionData, sectionName) {

        var obj = {};
        if (_.isArray(sectionData) && sectionData.length > 0) {
            obj[sectionName] = sectionData;
            sectionsWithNewContent.push(obj);
        } else if (_.isPlainObject(sectionData)) {

            // product is a special case
            if (sectionName === 'product') {
                return;
            }

            // section is completely new
            if (!_.has(inputModel.fileInfo.sections, sectionName)) {
                obj[sectionName] = sectionData;

            } else if (inputModel.fileInfo.sections[sectionName].length > 1 &&
                Object.keys(sectionData).length > 0 &&
                sectionName === PASS_THROUGH) {
                /* Section is an object that has been split across several files
                 * any remaining data needs to be written to a new file
                 * NOTE: We only care to do this for pass-through, since properties
                 * are pruned when writing out the other files, when writing other object-based sections
                 * no pruning is necessary
                 */
                obj[sectionName] = sectionData;

            } else {
                return;
            }
            sectionsWithNewContent.push(obj);
        }
    });
    return sectionsWithNewContent;
}

// Determine if each section element has its own file
function isSplitIntoEqualNumberOfFiles(sectionName, newInputModel) {
    var count = 0;
    _.forEach(newInputModel.fileInfo.fileSectionMap, function(file) {
        _.forEach(file, function(fileSection) {
            if (_.isObject(fileSection) && _.has(fileSection, sectionName) && fileSection[sectionName].length === 1) {
                count += 1;
            }
        });
    });
    return count === newInputModel.fileInfo.sections[sectionName].length;
}

function getSectionKeyName(sectionName, inputModel) {
    var fileContainingSection = _.find(inputModel.fileInfo.fileSectionMap, function(file) {
        return _.find(file, function(fileSection) {
            return _.isObject(fileSection) && _.has(fileSection, sectionName);
        });
    });

    var fileSection = _.find(fileContainingSection, function(section) {
        return _.isObject(section) && _.has(section, sectionName);
    });
    return fileSection.keyField;

}

function writeNewModelFile(sectionName, sectionData, inputModel, inputModelPath, newSection) {

    var fileName = sectionName.replace('-', '_');
    if (!newSection) {
        if (_.isArray(sectionData)) {
            var keyName = getSectionKeyName(sectionName, inputModel);

            if (_.isUndefined(keyName) || _.isNull(keyName)) {
                return Q.reject('Unable to find key name for section: ' + sectionName);
            }
            fileName = fileName + '_' + sectionData[0][keyName];
        } else {
            // In case of object sections add a random uuid to the fileName
            fileName = fileName + '_' + uuid.v1().substr(0, 8);
        }

    }

    fileName = fileName + '.yml';
    var fileContent = {};
    // All files have a product section
    fileContent.product = inputModel[INPUT_MODEL].product;
    fileContent[sectionName] = sectionData;
    var yamlEncodedContent = yaml.safeDump(fileContent, {noCompatMode: true});
    var filePath = path.join(inputModelPath, 'data', fileName).toLowerCase();
    logger.debug('Writing out file: ' + filePath);
    return writeFileQ(filePath, yamlEncodedContent, 'utf8');

}

/* After all files have been written to, check if there are any left over sections
 * any content in any section, must be new */
function writeNewModelData(newInputModel, inputModelPath) {

    var leftOverSections = extractLeftOverSections(newInputModel);
    var promises = [];
    _.forEach(leftOverSections, function(section) {

            var sectionName = Object.keys(section)[0];
            // check if section is new
            if (!_.has(newInputModel.fileInfo.sections, sectionName)) {
                // Section is new! Writing all its content to a new file
                if (_.isArray(section[sectionName])) {
                    promises.push(writeNewModelFile(sectionName, _.values(section[sectionName]),
                        newInputModel, inputModelPath, true));
                } else {
                    promises.push(writeNewModelFile(sectionName, section[sectionName],
                        newInputModel, inputModelPath, true));
                }

            } else {
                /* Section is not new, checking if section was
                 * previously split across different files, equally
                 * NOTE: this is only relevant to list sections */

                if (_.isArray(section[sectionName])) {
                    var splitIntoEqualNumberOfFiles = isSplitIntoEqualNumberOfFiles(sectionName, newInputModel);
                    if (splitIntoEqualNumberOfFiles) {
                        // each section element has its own file
                        _.forEach(section[sectionName], function(element) {
                            promises.push(writeNewModelFile(sectionName, [element], newInputModel, inputModelPath));
                        });
                        return;
                    }
                }

                /* Section is split over several files, but there isn't a 1-to-1 mapping
                 * Therefore, writing the remaining components into a single file
                 */
                if (_.isArray(section[sectionName])) {
                    promises.push(writeNewModelFile(sectionName, _.values(section[sectionName]),
                        newInputModel, inputModelPath));
                } else {
                    // non array section.. write out to a new file
                    promises.push(writeNewModelFile(sectionName, section[sectionName],
                        newInputModel, inputModelPath));
                }
            }
        }
    );
    return Q.all(promises);
}

function cleanEmptyParentProperties(object, pathElements) {

    // for (var i = pathElements.length; i > 0; i--) {
    //     var splicedArray = pathElements.splice(0, i);
    while (pathElements.length) {
        var pathString = pathElements.join('.');
        if (Object.keys(_.get(object, pathString)).length !== 0) {
            return;
        }
        // property is empty
        deleteNestedProperty(pathString, object, true);
        pathElements.length--;
    }

}

function deleteNestedProperty(path, object, skipEmptyPropCheck) {

    var pathElements = path.split('.');
    var tmp = object;
    for (var pathElem = 0; pathElem < pathElements.length - 1; pathElem++) {
        tmp = tmp[pathElements[pathElem]];
    }
    delete tmp[pathElements[pathElements.length - 1]];

    if (!skipEmptyPropCheck) {
        if (pathElements.length > 0) {
            pathElements.length--;
        }
        cleanEmptyParentProperties(object, pathElements);
    }
}

/*
 * Update Current Input Model
 */
function writeModel(argModel, modelPath) {

    var newInputModel = _.clone(argModel, true);

    // modelPath is only used by tests
    var inputModelPath = modelPath || this.inputModelPath;

    function dealWithListSection(fileSection, newContent) {
        var sectionName = _.without(_.keys(fileSection), 'keyField', 'type')[0];
        if (newInputModel.fileInfo.sections[sectionName].length === 1) {
            /* This section of the input model is maintained in a single file, therefore
             * write out all members of this section
             */
            newContent[sectionName] = newInputModel[INPUT_MODEL][sectionName];
            delete newInputModel[INPUT_MODEL][sectionName];
        } else {
            // This section is of the input model is maintained in several files
            _.forEach(_.keys(fileSection), function(fileSectionKey) {

                if (fileSectionKey === 'keyField') {
                    return;
                }
                var keyField = fileSection['keyField'];
                var keysToDelete = [];
                newContent[fileSectionKey] = _.filter(newInputModel[INPUT_MODEL][fileSectionKey],
                    function(obj) {
                        if (fileSection[fileSectionKey].indexOf(obj[keyField]) != -1) {
                            keysToDelete.push(obj[keyField]);
                            return true;
                        }
                        return false;
                    });
                _.remove(newInputModel[INPUT_MODEL][fileSectionKey],
                    _.partial(deleteValue, keysToDelete, keyField));
            });
        }
    }

    function dealWithObjectSection(fileSection, newContent) {

        var sectionName = _.pull(Object.keys(fileSection), 'type');
        if (sectionName.length !== 1) {
            throw 'Unexpected fileInfo content!';
        }
        sectionName = sectionName[0];

        var sectionData = {};
        _.each(fileSection[sectionName], function(property) {
            // pluck properties from the template and add them to sectionData
            var value = _.get(newInputModel[INPUT_MODEL][sectionName], property);
            if (!_.isUndefined(value)) {
                _.set(sectionData, property, value);

                // remove property from newInputModel, only for pass-through
                if (sectionName === PASS_THROUGH) {
                    deleteNestedProperty(property, newInputModel[INPUT_MODEL][sectionName]);
                }

            }
        });

        if (Object.keys(sectionData).length > 0) {
            newContent[sectionName] = sectionData;
        }
    }

    function writeOutSection(file) {
        var fileSections = newInputModel.fileInfo.fileSectionMap[file];
        var newContent = {};
        _.forEach(fileSections, function(fileSection) {
            try {
                if (!_.isPlainObject(fileSection)) {
                    newContent[fileSection] = newInputModel[INPUT_MODEL][fileSection];
                } else {
                    if (fileSection.type === 'array') {
                        dealWithListSection(fileSection, newContent);
                    } else if (fileSection.type === 'object') {
                        dealWithObjectSection(fileSection, newContent);
                    } else {
                        // This shouldn't happen!
                        logger.warn('What is file section? ' + JSON.stringify(fileSection));
                    }
                }
            } catch (err) {
                console.trace(err);
                throw 'Failed to write out section: ' + JSON.stringify(fileSection) + ' to file: ' + file;
            }
        });
        // empty file check
        var keys = Object.keys(newContent);
        if (keys.length > 1 || (keys.length === 1 && keys[0] !== 'product')) {
            var yamlEncodedContent = yaml.safeDump(newContent, {noCompatMode: true});
            // make sure nested directories exist when writing out the file
            logger.debug('Writing out file: ' + path.join(inputModelPath, file));
            return Q.nfcall(mkdirp, path.dirname(path.join(inputModelPath, file)))
                .then(_.partial(writeFileQ, path.join(inputModelPath, file), yamlEncodedContent, 'utf8'));
        } else {
            logger.debug('Skipping empty file: ' + file);
        }

    }

    function writeSections() {
        var promises = [];
        _.forEach(_.keys(newInputModel.fileInfo.fileSectionMap), function(relativeFilePath) {
            promises.push(writeOutSection(relativeFilePath));
        });
        return Q.all(promises);
    }

    return wiperModelDir(inputModelPath)
        .then(writeSections)
        .then(_.partial(writeNewModelData, newInputModel, inputModelPath))
        .catch(function(err) {
            logger.error('Failed to write model due to: ' + err);
        });
}

function wiperModelDir(modelPath) {
    var dirStack = [];

    return Q.nfcall(walk.walk, modelPath, function(basedir, filename, stat, next) {
        if (stat.isFile() && path.extname(filename) === constants.YML_EXT) {
            logger.debug('Deleting file: ' + path.join(basedir, filename));
            fs.unlink(path.join(basedir, filename));
        } else if (stat.isDirectory()) {
            dirStack.push(path.join(basedir, filename));
        }
        next();
    }).then(function() {
        // check if dirStack contains directories which are now empty
        var val = dirStack.pop();
        while (!_.isUndefined(val)) {
            var files = fs.readdirSync(val);
            if (files.length === 0) {
                logger.debug('Deleting empty directory: ' + val);
                fs.rmdirSync(val);
            }
            val = dirStack.pop();
        }

    }).catch(function(err) {
        if (err.code == 'ENOENT') {
            return;
        }
        return err;
    });
}

ModelWriter.prototype.writeModel = writeModel;

module.exports = ModelWriter;
