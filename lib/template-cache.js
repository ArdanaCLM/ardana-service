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

exports.init = init;
exports.templates = [];
exports.templateMap = {};
exports.templateNames = [];
exports.isInitialised = isInitialised;

//////////

// List of folder names to ignore
var IGNORE = ['examples.old'];

var constants = require('./constants');
var path = require('path');
var fs = require('fs');
var _ = require('lodash');
var reader = require('./model-reader');
var logger = require('./logger');
var Q = require('q');

var readdirQ = Q.denodeify(fs.readdir);

var initialised = false;

function scanForTemplates(root) {
    return readdirQ(root).then(function(files) {
        var promises = [];
        _.each(files, function(file) {
            var filePath = path.join(root, file);
            var fileMetadata = fs.statSync(filePath);
            if (fileMetadata.isDirectory()) {
                if (!_.includes(IGNORE, file)) {
                    promises.push(scanForTemplates(filePath));
                } else {
                    logger.debug('Ignoring: ' + filePath);
                }
            } else if (file === constants.CLOUD_CONFIG) {

                promises.push(reader.readTemplate(root).then(function(template) {
                    if (template.name in exports.templateMap) {
                        logger.debug('! Duplicate template name - template already exists: ' + template.name);
                        logger.debug('        Duplicate: ' + filePath);
                        logger.debug('        Existing: ' + exports.templateMap[template.name].configFile);
                    } else {
                        logger.debug('Successfully cached template: ' + template.name);
                        exports.templates.push(template);
                        exports.templateMap[template.name] = template;
                        exports.templateNames.push(template.name);
                    }
                }));

            }
        });
        return Q.all(promises).then(function() {
            initialised = true;
        });
    });

}

function isInitialised() {
    return initialised;
}

function init(config) {
    // Recurse file system looking for templates
    logger.debug('Looking for templates');
    initialised = false;
    exports.templates = [];
    exports.templateMap = {};
    exports.templateNames = [];

    return scanForTemplates(config.get('paths:templatesDir'));
}
