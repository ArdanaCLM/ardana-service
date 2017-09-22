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
exports.getApiPath = function() {
    return TEMPLATES_PATH;
};

//////////

var path = require('path');
var fs = require('fs');
var _ = require('lodash');
var Q = require('q');

var cache = require('../lib/template-cache');
var graphGenerator = require('../lib/graph-gen');
var utils = require('../lib/utils');

var TEMPLATES_PATH = '/templates';

var apiEndpoint;

function init(router, config) {

    apiEndpoint = config.get('apiEndpoint');

    function emptyCacheHandler(response, error) {
        utils.sendErrorResponse(response, 'Template cache failed to initialise', error, 404);
    }

    function checkTemplateCache(response) {
        if (!cache.isInitialised()) {
            return cache.init(config).catch(_.partial(emptyCacheHandler, response));
        }
        return Q.when();
    }


    // Get list of all templates
    router.get(TEMPLATES_PATH, function(request, response) {
        checkTemplateCache(response).then(function() {
            var result = [];
            _.each(cache.templateNames, function(name) {
                result.push({
                    name: name,
                    href: apiEndpoint + TEMPLATES_PATH + '/' + name,
                    overview: cache.templateMap[name].readme.html
                });
            });
            response.json(result);
        });
    });


    // Get template with given id/name
    router.get(TEMPLATES_PATH + '/:id', function(request, response) {
        checkTemplateCache(response).then(function() {
            var id = request.params.id;
            var template = cache.templateMap[id];
            if (template) {
                response.json(template);
            } else {
                utils.sendErrorResponse(response, {}, 'Template with id \'' + id + '\' not found', 404);
            }
        });
    });

    // Get template with given id/name as a graph
    router.get(TEMPLATES_PATH + '/:id/graph', function(request, response) {
        checkTemplateCache(response).then(function() {
            var id = request.params.id;
            var template = cache.templateMap[id];
            if (template) {
                if (request.query.jsonp) {
                    var str = 'var ' + request.query.jsonp + '=';
                    str += JSON.stringify(graphGenerator.generate(template));
                    str += ';';
                    response.set('Content-Type', 'application/javascript');
                    response.send(str);
                } else {
                    response.json(graphGenerator.generate(template));
                }
            } else {
                utils.sendErrorResponse(response, {}, 'Template with id \'' + id + '\' not found', 404);
            }
        });
    });
}
