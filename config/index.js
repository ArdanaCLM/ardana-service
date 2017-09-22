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

var nconf = require('nconf');
var yaml = require('js-yaml');
var fs = require('fs');
var _ = require('lodash');
var path = require('path');

// Matcher for performing string interpolation in the config using ${var} syntax
var VARIABLE_MATCHER = new RegExp('\\${(.*)}', 'g');

function loadYamlFile(filePath) {
    return yaml.safeLoad(fs.readFileSync(filePath));
}

function fileExists(filePath) {
    try {
        return fs.statSync(filePath).isFile();
    } catch (err) {
        return false;
    }
}

/** Replace instances of ${var} in the passed string with the value of var */
function resolveVariable(string) {
    var matches = VARIABLE_MATCHER.exec(string);
    while (matches) {
        var variable_name = matches[1];
        var variable_value = nconf._get(variable_name);
        string = string.replace(VARIABLE_MATCHER, variable_value);
        matches = VARIABLE_MATCHER.exec(string);
    }
    return string;
}

/** Recursively perform String interpolation in the passed Object */
function interpolate(obj) {
    if (_.isString(obj)) {
        obj = resolveVariable(obj);
    } else if (_.isPlainObject(obj)) {
        obj = _.mapValues(obj, interpolate);
    } else if (_.isArray(obj)) {
        obj = _.map(obj, interpolate);
    }
    return obj;
}

// We need to have a store set before we can write
nconf.use('memory');

/** load command line arguments **/
nconf.argv();
/** load environment variables **/
nconf.env();


/** if -c param has been specified use that as path for venv config.yml **/
var configFile = nconf.get('config');
if (!configFile || !fileExists(configFile)) {
    var configFileBase = 'config.yml';
    if (fileExists(configFileBase)) {
        configFile = configFileBase;
    }
}

if (configFile) {
    fs.accessSync(configFile);
    nconf.file({
        file: configFile,
        format: require('nconf-yaml')
    });
}

// load defaults
nconf.defaults(loadYamlFile(path.join(__dirname, 'config-defaults.yml')));

// Rename original nconf.get() for our use in the overridden version
nconf._get = nconf.get;

// Override nconf.get() to perform recursive String interpolation
nconf.get = function(path) {
    return interpolate(nconf._get(path));
};

nconf.override = function(propertyPath, value) {
    nconf.set(propertyPath, value);
};

nconf.isDev = function() {
    return isDev;
};

nconf.isMocked = function() {
    return (typeof(nconf.get('testing:mock')) === 'string') ?
        (nconf.get('testing:mock') === 'true') : nconf.get('testing:mock');
};

// Initialised state
var isDev = nconf.get('env') === 'development';
if (isDev && !nconf.isMocked() && !nconf.get('deployer:remote')) {
    throw 'Dev mode but a deployer:remote is not configured!';
}

// Initialise version
try {
    // Always try and read a local .version file
    var versionString = fs.readFileSync('.version', 'utf8');
    nconf.set('version', versionString);
} catch (readFileError) {
    if (isDev) {
        // We may be running direct from git source
        try {
            var git = require('gift');
            var giftInstance = git(path.join(__dirname, '..'));
            giftInstance.current_commit(function(giftError, commit) {
                if (giftError) {
                    return nconf.set('version', 'failed to get any version info');
                }
                nconf.set('version', 'dev - git commit: ' + commit.id);
            });
        } catch (shouldNotHappen) {
            nconf.set('version', 'failed to get any version info');
        }
    } else {
        nconf.set('version', 'failed to parse the .version file');
    }
}


module.exports = nconf;
