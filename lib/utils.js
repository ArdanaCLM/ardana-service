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

var logger = require('../lib/logger');
var _ = require('lodash');
var fs = require('fs');
var Q = require('q');

var statQ = Q.denodeify(fs.stat);

function sendErrorResponse(response, error, message, statusCode) {
    // err can be created as below (all properties are optional)
    //var userError = {
    //    isUserError: 'User friendly text describing the error of their ways, this will make it into the notification',
    //    errorCode: error code as per constants.ERROR_CODES
    //}
    //var nonUserError = {
    //    isUserError: falsy,
    //    errorCode: error code as per constants.ERROR_CODES
    //}

    // FIXME: surely the error Object could contain a message property directly instead of realying on isUserError?
    message = _.get(error, 'isUserError') ? error.isUserError : message;
    logger.error(message, error);

    error = error || {};

    // Status code can be passed in directly as an argument or embedded inside a user error
    response.status(statusCode || error.statusCode || (error.isUserError ? 400 : 500));
    if (error.statusCode) {
        delete error.statusCode;
    }

    var json = {
        message: message
    };

    // Error code is included in error object. The source/location of error may be nested deep in library files a long
    // distance from where this function is called.
    if (_.get(error, 'code')) {
        json.errorCode = error.code;
    }

    // The error object may contain sensitive data, only return if it's process meta data
    // TODO: investigate better approach for pRef process errors
    if (_.get(error, 'pRef')) {
        json.error = error;
    }

    response.json(json);
}


function endsWith(str, suffix) {
    return str.indexOf(suffix, str.length - suffix.length) !== -1;
}

// Return a new Object identical to obj where keys have been recursively sorted alphabetically
function sortKeys(obj) {
    if (!_.isPlainObject(obj)) {
        return obj;
    }
    var sortedObj = {};
    var sortedKeys = Object.keys(obj).sort(function(key1, key2) {
        return key1.toLowerCase().localeCompare(key2.toLowerCase());
    });
    for (var i = 0; i < sortedKeys.length; i++) {
        sortedObj[sortedKeys[i]] = sortKeys(obj[sortedKeys[i]]);
    }
    return sortedObj;
}

/**
 * Check whether a param was specified in a query
 * @param {Object} query - the query from an Express request
 * @param {string} paramName - the name of the param to check
 * @return {boolean} true if the param was specified in the request
 * */
function hasParam(query, paramName) {
    return !_.isUndefined(query[paramName]);
}

/**
 * Parse the value of a query param as a boolean. A tad OTT...
 * @param {Object} query - the query from an Express request
 * @param {string} paramName - the name of the param to check
 * @return {boolean} true if the param was specified in the request and either:
 * - has no value (used as a flag)
 * - is the string 'true'
 * */
function parseBoolParam(query, paramName) {

    // If the parameter is missing altogether, default to false
    if (!hasParam(query, paramName)) {
        return false;
    }

    var value = query[paramName];

    switch (value.toLowerCase()) {
        case '': // If the value is the empty string, parameter was specified as a flag
        case 'true':
        case '1':
            return true;
        case 'false':
        case '0':
            return false;
        default:
            // any other value is gibberish... Fail as we have no clue what the user wants
            throw {
                isUserError: "bad value: '" + value + "' specified for boolean query parameter: '" + paramName + "'",
                statusCode: 400
            };
    }
}

/**
 * Parse the value of a query param as an Integer
 * @param {Object} query - the query from an Express request
 * @param {string} paramName - the name of the param to check
 * @return {boolean} the integer value if the param was specified as a legit integer
 * @throws error if the param was specified and not an integer
 * */
function parseIntParam(query, paramName) {

    // If the parameter is missing altogether, return undefined
    if (!hasParam(query, paramName)) {
        return undefined;
    }

    var value = query[paramName];
    var ret = parseInt(value, 10);
    if (isNaN(ret)) {
        throw {
            isUserError: "bad value: '" + value + "' specified for integer query parameter: '" + paramName + "'",
            statusCode: 400
        };
    }
    return ret;
}

exports.endsWith = endsWith;
exports.sendErrorResponse = sendErrorResponse;
exports.sortKeys = sortKeys;
exports.hasParam = hasParam;
exports.parseBoolParam = parseBoolParam;
exports.parseIntParam = parseIntParam;
