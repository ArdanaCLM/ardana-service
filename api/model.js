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
exports.writeModel = writeModel;
exports.getApiPath = function() {
    return MODEL_PATH;
};

var _ = require('lodash');

var constants = require('../lib/constants');
var utils = require('../lib/utils');
var currentInputModel = require('../lib/current-input-model');

var MODEL_PATH = '/model';
var CHANGES_PATH = MODEL_PATH + '/changes';
var ENTITIES_PATH = MODEL_PATH + '/entities';

var INPUT_MODEL = constants.INPUT_MODEL;

function writeModel(model, response) {
    var written = currentInputModel.writeModel(model);
    if (response) {
        return written.then(function() {
            response.status(201).send();
        }).catch(function(error) {
            utils.sendErrorResponse(response, error, 'Failed to write input model');
            throw error;
        });
    }
    return written;
}

function init(router) {

    // Retrieve the current input model
    router.get(MODEL_PATH, function(request, response) {
            currentInputModel.getModel()
            .then(function(model) {
                response.json(model);
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to get input model');
            });
    });

    // Check whether the readied model was encrypted using ansible-vault
    router.get(MODEL_PATH + '/is_encrypted', function(request, response) {
        currentInputModel.isEncrypted()
            .then(function(isEncrypted) {
                response.json({isEncrypted: isEncrypted});
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to check if the model was encrypted');
            });
    });

    // Retrieve the expanded input model (output of the Config Processor)
    router.get(MODEL_PATH + '/expanded', function(request, response) {
        utils.sendErrorResponse(response, {isUserError: 'This API has been removed. ' +
        'Please use /model/cpoutput', statusCode: 404});
    });

    // Retrieve the expanded input model and look for a server by ID within server-groups
    router.get(MODEL_PATH + '/expanded/servers/:id', function(request, response) {
        utils.sendErrorResponse(response, {isUserError: 'This API has been removed. ' +
        'Please use /model/cpoutput', statusCode: 404});
    });


    // Replace the input model (currently this requires the model envelope with fileInfo etc.)
    router.post(MODEL_PATH, function(request, response) {
        writeModel(request.body, response);
    });

    // Stage all changes and create a new git commit for the current input model
    router.post(MODEL_PATH + '/commit', function(request, response) {
            currentInputModel.commit(request.body.message)
            .then(function(commit) {
                response.status(201).json(commit);
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to commit input model');
            });
    });

    // Retrieve the input model git history
    router.get(MODEL_PATH + '/history', function(request, response) {
        currentInputModel.getHistory()
            .then(function(commits) {
                response.json(commits);
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Failed to get input model git history');
            });
    });

    // Get the git state for the current input model
    router.get(MODEL_PATH + '/state', function(request, response) {
            currentInputModel.getState()
            .then(function(obj) {
                response.json(obj);
            })
            .catch(function(error) {
                utils.sendErrorResponse(response, error, 'Could not determine the state of the input model');
            });
    });

    // List unstaged and uncommitted changes
    router.get(CHANGES_PATH, function(request, response) {
        response.json({TODO: 'Not yet implemented'});
    });

    // Revert unstaged and uncommitted changes
    router.delete(CHANGES_PATH, function(request, response) {
        currentInputModel.clean().then(function() {
            response.status(204).send();
        }, function(error) {
            utils.sendErrorResponse(response, error, 'Failed to clean input model.');
        });
    });

    // For a given entity, build a map of routes allowed
    function buildEntityRoutes(entityName, entity) {
        var ret = {
            get: 'GET ' + ENTITIES_PATH + '/' + entityName,
            update: 'PUT ' + ENTITIES_PATH + '/' + entityName
        };
        if (_.isArray(entity)) {
            ret['add'] = 'POST ' + ENTITIES_PATH + '/' + entityName;
            ret['getById'] = 'GET ' + ENTITIES_PATH + '/' + entityName + '/:id';
            ret['updateById'] = 'PUT ' + ENTITIES_PATH + '/' + entityName + '/:id';
            ret['deleteById'] = 'DELETE ' + ENTITIES_PATH + '/' + entityName + '/:id';
        }
        return ret;
    }

    /**
     * Read the model and extract a named entity from it.
     * @param {string} entityName the name of the top-level entity to read
     * @return {promise} a promise resolved with [model, entity]
     * Note: You can use .spread(model, entity) on the returned promise to access the model and entity
     * */
    function getEntity(entityName) {
        return currentInputModel.getModel().then(function(model) {
            var inputModel = model[INPUT_MODEL];
            if (!inputModel.hasOwnProperty(entityName)) {
                throw {
                    isUserError: "Entity '" + entityName + "' not found",
                    statusCode: 404
                };
            }
            return [model, inputModel[entityName]];
        });
    }

    /**
     * Read the model, replace the named entity with the specified Object and write the model back
     * @param {string} entityName the name of the top-level entity to replace
     * @param {Object} entity the new value for the entity
     * */
    function replaceEntity(entityName, entity) {
        return currentInputModel.getModel().then(function(model) {
            var inputModel = model[INPUT_MODEL];
            if (!inputModel.hasOwnProperty(entityName)) {
                throw {
                    isUserError: "Entity '" + entityName + "' not found",
                    statusCode: 404
                };
            }
            inputModel[entityName] = entity;
            return writeModel(model);
        });
    }

    /** Throws error if passed entity is not an array */
    function checkArrayType(entityName, entity) {
        if (!_.isArray(entity)) {
            throw {
                isUserError: "Entity '" + entityName + "' not an array",
                statusCode: 400
            };
        }
    }

    function getIndexById(entityName, entity, id) {
        if (_.isUndefined(id)) {
            throw {
                isUserError: 'ID must be specified in the request',
                statusCode: 400
            };
        }
        var idField = currentInputModel.getIdKey(entity[0]);
        var index = _.findIndex(entity, function(entityMember) {
            return entityMember[idField] === id;
        });
        if (index < 0) {
            throw {
                isUserError: entityName.slice(0, -1) + " with id '" + id + "' not found",
                statusCode: 404
            };
        }
        return index;
    }

    // Dynamically list available model entities and the operations allowed on each
    router.get(ENTITIES_PATH, function(request, response) {
        currentInputModel.getModel().then(function(model) {
            var ret = {};
            _.forEach(model[INPUT_MODEL], function(value, key) {
                ret[key] = buildEntityRoutes(key, value);
            });
            response.json(ret);
        });
    });

    // Get an entire entity
    router.get(ENTITIES_PATH + '/:entity', function(request, response) {
        var entityName = request.params.entity;

        getEntity(entityName).spread(function(model, entity) {
            response.json(entity);
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Update an entire entity
    router.put(ENTITIES_PATH + '/:entity', function(request, response) {
        var entityName = request.params.entity;
        var newValue = request.body;

        replaceEntity(entityName, newValue).then(function() {
            response.status(204).send();
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Get a value by id from an array-entity
    router.get(ENTITIES_PATH + '/:entity/:id', function(request, response) {
        var entityName = request.params.entity;
        var id = request.params.id;

        getEntity(entityName).spread(function(model, entity) {
            checkArrayType(entityName, entity);
            response.json(entity[getIndexById(entityName, entity, id)]);
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Update a value by id from an array-entity
    router.put(ENTITIES_PATH + '/:entity/:id', function(request, response) {
        var newValue = request.body;
        var entityName = request.params.entity;
        var id = request.params.id;

        getEntity(entityName).spread(function(model, entity) {
            checkArrayType(entityName, entity);
            entity[getIndexById(entityName, entity, id)] = newValue;
            return writeModel(model).then(function() {
                response.status(204).send();
            });
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Delete a value by id from an array-entity
    router.delete(ENTITIES_PATH + '/:entity/:id', function(request, response) {
        var entityName = request.params.entity;
        var id = request.params.id;

        getEntity(entityName).spread(function(model, entity) {
            checkArrayType(entityName, entity);

            var index = getIndexById(entityName, entity, id);
            entity.splice(index, 1);
            return writeModel(model).then(function() {
                response.status(204).send();
            });
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

    // Add a value to an array-entity
    router.post(ENTITIES_PATH + '/:entity', function(request, response) {
        var newValue = request.body;
        var entityName = request.params.entity;

        getEntity(entityName).spread(function(model, entity) {
            checkArrayType(entityName, entity);

            // If the array is not empty, check for duplicate id before adding
            if (entity.length > 0) {
                var idField = currentInputModel.getIdKey(entity[0]);
                var index = _.findIndex(entity, function(entityMember) {
                    return entityMember[idField] === newValue[idField];
                });
                if (index !== -1) {
                    throw {
                        isUserError: entityName.slice(0, -1) + " with id '" + newValue[idField] + "' already exists",
                        statusCode: 400
                    };
                }
            }

            entity.push(newValue);

            return writeModel(model).then(function() {
                response.status(201).send();
            });
        }).catch(function(error) {
            utils.sendErrorResponse(response, error);
        });
    });

}
