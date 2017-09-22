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

var WebSocketServer = require('ws').Server;
var logger = require('./logger');
var _ = require('lodash');

// Currently active WebSocket clients
var webSocketClients = {};

// Simple incrementing ID for websocket clients
var websocketClientId = 0;

var actionHandlers = {};
var clientDisconnectHandlers = [];

var MESSAGE_TYPES = {
    LOG_DATA: 'logData',
    PROCESS_END: 'processEnd',
    PROCESS_START: 'processStart',
    INPUT_MODEL_CHANGE: 'inputModelChange'
};

function startWebSocketServer(server) {
    var webSocketServer = new WebSocketServer({server: server, path: '/logs'});
    attachWebSocketHandlers(webSocketServer);
}

function attachWebSocketHandlers(webSocketServer) {
    webSocketServer.on('connection', function connection(webSocketClient) {
        logger.info('Client opened a WebSocket connection!');

        var clientId = ++websocketClientId;
        webSocketClients[clientId] = webSocketClient;

        webSocketClient.on('message', function incoming(data) {
            logger.debug('Received message from WebSocket client:', data);

            var message = JSON.parse(data);

            if (!_.has(actionHandlers, message.action)) {
                logger.error('No action handlers for action: ' + message.action);
            } else {
                actionHandlers[message.action](message, clientId);
            }

        });

        webSocketClient.on('close', function close(code, message) {
            logger.info('Client closed WebSocket connection - Code: ' +
                code + (message ? ' - Message: ' + message : ''));
            _.forEach(clientDisconnectHandlers, function(clientDisconnectHandler) {
                clientDisconnectHandler(clientId);
            });
        });

        // Let's be polite with our new client
        webSocketClient.send('Bonjour mon cher client!');
    });
}


var addActionHandler = function(action, messageHandler) {
    logger.debug('Adding action handler for: ' + action);
    actionHandlers[action] = messageHandler;
};

var addClientDisconnectHandler = function(clientDisconnectHandler) {
    clientDisconnectHandlers.push(clientDisconnectHandler);
};

module.exports.MESSAGE_TYPES = MESSAGE_TYPES;
module.exports.webSocketClients = webSocketClients;

/** Add hook for handling specific actions when a new client connects **/
module.exports.addActionHandler = addActionHandler;

/** Add hook for handling client disconnection **/
module.exports.addClientDisconnectHandler = addClientDisconnectHandler;

module.exports.start = startWebSocketServer;
