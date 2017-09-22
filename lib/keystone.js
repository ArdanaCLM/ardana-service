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

var _ = require('lodash');
var fs = require('fs');
var Q = require('q');
var needle = require('needle');
var path = require('path');
var logger = require('./logger');

var X_AUTH_HEADER = 'x-auth-token';
var X_SUBJECT_HEADER = 'x-subject-token';
var MAX_CACHE_ENTRIES = 25;

// Skip auth for heartbeats
var apiMountPoint;
var heartbeatEndpoint;
var versionEndpoint;

// ----------------------------------------------------------------------------------------
// Required Keystone configuration

// We need URL to talk to keystone (and ca_cert_file if using TLS)
// We need everything else in order to get a token that we can use to verify other tokens
var keystone_config = {};

// Disable authentication altgother - must be explicitly set by config
var keystone_disabled = false;

// Is the config valid?
var keystone_config_valid = false;

var required_config_params = ['auth_url', 'project_name', 'project_domain_name',
    'username', 'user_domain_name', 'password'];

// ----------------------------------------------------------------------------------------

// Contents of the specified ca certs file if used - only read if we have file path and we are using HTTPS
var ca_certs;

// Cache of tokens to token metadata
var cache = {};

// We will only cache this number of entries (LRU)
var maxCacheEntries = MAX_CACHE_ENTRIES;

// This is our admin token that we will use to verify other tokens - this will
// expire just like other tokens
// To start we set to a value that is not valid which will force us to get a new token
// the first time we need to validate a request
var keystone_admin_token = 'ARDANA_SERVICE_SERVICES_INIT_TOKEN';

var _setConfig = function(config) {
    keystone_config = config;

    // If Keystone was explicitly disabled, bail early
    keystone_disabled = !!keystone_config.disabled;
    if (keystone_disabled) {
        return;
    }

    // Check that we have all of the required configuration parameters
    var missingProperties = _.difference(required_config_params, Object.keys(keystone_config));
    keystone_config_valid = missingProperties.length === 0;

    if (!keystone_config_valid) {
        logger.error('Keystone config is invalid! The following required properties are missing:', missingProperties);
        return;
    }

    // Only read the certificate if we are using HTTPS
    if (keystone_config.ca_cert_file && keystone_config.auth_url.toLowerCase().indexOf('https') === 0) {
        ca_certs = fs.readFileSync(keystone_config.ca_cert_file);
    }

    maxCacheEntries = keystone_config.maxCacheEntries ? keystone_config.maxCacheEntries : MAX_CACHE_ENTRIES;

    logger.debug('Keystone config is valid');
};

var _sendError = function(res, code, text) {
    res.set('Content-Type', 'text/plain');
    res.status(code).send(text);
};

// Have we cached this token? If so, is it still valid (not expired)?
var _haveValidCachedToken = function(token) {
    var tokenData = cache[token];
    if (!tokenData || !tokenData.expiry) {
        return false;
    }
    // We have a cached token, so check to see if the token has expired
    var now = new Date();
    if (tokenData.expiry < now) {
        // token has expired
        delete cache[tokenData.token];
        return false;
    } else {
        return true;
    }
};

// Cache the given token and ensure that the cache does not exceed the maximum number of entries
var _cacheToken = function(token, tokenInfo) {
    if (tokenInfo.expires_at) {
        var expiry = new Date(tokenInfo.expires_at);
        cache[token] = {
            token: token,
            expiry: expiry
        };

        // Prune cache if needed to keep it within the maximum number of entries
        if (Object.keys(cache).length > maxCacheEntries) {
            // Need to remove the oldest entry
            var sorted = _.sortBy(cache, function(o) {
                return o.expiry;
            });
            // Remove the first in the queue (sorted oldest first)
            if (sorted.length > 0) {
                delete cache[sorted[0].token];
            }
        }
    }
};

// Allows a CA Cert chain to be used (useful if using self-signed certificates)
var _addCACertOptionIfNeeded = function(options) {
    if (ca_certs) {
        options.ca = ca_certs;
    }
    return options;
};

// Get an admin token that we can use to validate user tokens
var _getAdminToken = function() {
    // Keystone Request body to get a new Admin token
    var body = {
        auth: {
            identity: {
                methods: ['password'],
                password: {
                    user: {
                        name: keystone_config.username,
                        domain: { name: keystone_config.user_domain_name },
                        password: keystone_config.password
                    }
                }
            },
            scope: {
                project: {
                    name: keystone_config.project_name,
                    domain: { name: keystone_config.project_domain_name }
                }
            }
        }
    };

    var options = _addCACertOptionIfNeeded({
        json: true
    });

    // POST to the Keystone endpoint
    return Q.nfcall(needle.post, keystone_config.auth_url + '/auth/tokens', body, options).spread(function(response) {
        if (response.statusCode === 200 || response.statusCode === 201) {
            // Check for token in the Header
            var token = response.headers[X_SUBJECT_HEADER];
            if (token && token.length) {
                logger.debug('Successfully obtained a new admin token');
                keystone_admin_token = token;
                return keystone_admin_token;
            }
        }
        // This should not happen
        throw 'Failed to get admin token for token validation';
    }, function(error) {
        // Very unlikely to reach this as it would mean Keystone crashed after our first successful call
        throw 'Failed to get admin token, we experienced an error communicating with Keystone';
    });

};

var _verifyToken = function(token, allowAdminTokenFetch) {

    // Async verification - we need to call Keystone
    var options = _addCACertOptionIfNeeded({
        headers: {},
        parse_response: true
    });

    options.headers[X_AUTH_HEADER] = keystone_admin_token;
    options.headers[X_SUBJECT_HEADER] = token;

    // Make the request to keystone
    return Q.nfcall(needle.get, keystone_config.auth_url + '/auth/tokens?nocatalog', options)
        .spread(function(response) {

            // 401 means that our admin token is invalid (initial case or has expired) so we need to get another
            if (response.statusCode === 401) {
                if (allowAdminTokenFetch) {
                    logger.debug('Our admin token is invalid (initial case or has expired)');
                    return _getAdminToken().then(function() {
                        return _verifyToken(token, false);
                    });
                }
                // We'd get an endless loop if we *somehow* keep getting an admin token that fails
                throw 'Admin token is not valid for token validation';
            }

            if (response.statusCode !== 200) {
                // Failed
                throw 'Unauthorized: The supplied token is not valid';
            }

            var info = response.body;
            if (info && info.token && info.token.expires_at) {
                // Success - cache this token for later
                _cacheToken(token, info.token);
                return info;
            }
            // This shouldn't happen unless keystone is broken
            throw 'Token validation response did not contain expected metadata';

        }, function(error) {
            // We probably cannot communicate with keystone at all
            throw 'Token validation experienced an error communicating with Keystone';
        });
};

// Main middleware function
var middleware = function(req, res, next) {
    if (keystone_disabled) {
        return next();
    }

    // Don't authenticate requests which are not part of our API (e.g. favicon)
    if (req.path.indexOf(apiMountPoint) !== 0) {
        return next();
    }

    // Heartbeat requests don't need authentication
    if (req.path === heartbeatEndpoint) {
        return next();
    }

    // Version requests don't need authentication
    if (req.path === versionEndpoint) {
        return next();
    }

    if (!keystone_config_valid) {
        return _sendError(res, 401, 'Unauthorised: Invalid Keystone configuration; can not authenticate request');
    }

    // Check for the Authentication header
    var token = req.headers ? req.headers[X_AUTH_HEADER] : undefined;
    if (!token || !token.length) {
        // Auth header is required
        return _sendError(res, 401, 'Unauthorised: Authentication required but no X-Auth-Token header was supplied');
    }

    // Look to see if we have a cached token that is still valid
    if (_haveValidCachedToken(token)) {
        return next();
    }

    // Need to go and verify the token again with Keystone
    logger.debug('Verifying new client token...');
    _verifyToken(token, true).then(function() {
        logger.debug('Client token is valid');
        return next();
    }).catch(function(error) {
        logger.info(error);
        _sendError(res, 401, error);
    });
};

// The module exports the middleware function for use by app.use();
module.exports = function(config) {
    // Get the keystone configuration from the config passed in, if it is available
    if (config.get('keystone_config')) {
        _setConfig(config.get('keystone_config'));
    } else {
        logger.warn('keystone_config section is missing, requests will be failed');
    }

    apiMountPoint = config.get('apiEndpoint');
    heartbeatEndpoint = path.join(apiMountPoint, 'heartbeat');
    versionEndpoint = path.join(apiMountPoint, 'version');

    return middleware;
};
