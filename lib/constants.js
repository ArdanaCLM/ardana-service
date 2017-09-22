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

//////////

var constants = {
    VERSION: 2,
    CLOUD_CONFIG: 'cloudConfig.yml',
    DATA_DIR_KEY: 'data-dir',
    UTF8: 'utf8',
    PRODUCT: 'product',
    INPUT_MODEL: 'inputModel',
    CP_VERSION: '2.0',
    YML_EXT: '.yml',
    HTML_EXT: '.html',
    MD_EXT: '.md',
    README: 'README',
    ERROR_CODES: {
        // Note: is this truly an error or should we reply in the 2xx range?
        // When attempting to stage and commit but there are no unstaged changes
        COMMIT_NO_CHANGES: {
            code: 1
        },
        // When attempting to run through the process an error occurred at the commit stage
        PROCESS_COMMIT: {
            code: 100
        },
        // When attempting to run through the process an error occurred at the validate/config-processor-run stage
        PROCESS_VALIDATE: {
            code: 101
        },
        // When attempting to run through the process an error occurred at the ready_deployment stage
        PROCESS_READY_DEPLOYMENT: {
            code: 102
        },
        // When attempting to run through the process an error occurred during one of many deploy steps
        PROCESS_DEPLOY: {
            code: 103
        },
        // When attempting to run through the process an error occurred at the site --tag generate_hosts_file stage
        PROCESS_GEN_HOSTS_FILE: {
            code: 106
        },
        // When attempting to run through the process an error occurred at the monasca-deploy --tag
        // active_ping_checks stage
        PROCESS_MONASCA_CHECK: {
            code: 107
        },
        // Validation/config-processor-run failed, input model invalid
        PROCESS_VALIDATE_INVALID: {
            code: 104
        },
        // Cannot execute concurrent requests to run through the process
        PROCESS_CONCURRENT: {
            code: 105
        },
        // Cannot make concurrent requests to servers endpoint for certain child endpoints
        SERVERS_CONCURRENT: {
            code: 200
        },
        // Cannot run ansible playbook, detected concurrent processes running
        CONCURRENT_PROCESS_RUNNING: {
            code: 1001
        },
        // Cannot run ansible playbook, service is shutting down
        SHUTTING_DOWN: {
            code: 1002
        }
    },
    BAREMETAL_CONFIG_FILENAME: 'servers.yml'
};

module.exports = constants;
