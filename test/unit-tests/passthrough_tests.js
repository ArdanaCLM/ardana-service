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
var _ = require('lodash');
var should = require('should');
var config = require('../../config');
var path = require('path');
var reader = require('../../lib/model-reader');
var Writer = require('../../lib/model-writer');
var constants = require('../../lib/constants');
var exec = require('child_process').exec;
var fs = require('fs');
var mkdirp = require('mkdirp');
var temp = require('temp');
var Q = require('q');
var yaml = require('js-yaml');
var modelWriter = new Writer(config);

var midSizeExamplePath = path.join(__dirname, '..', 'temp', 'ardana-input-model',
    '2.0', 'examples', 'mid-scale-kvm-vsa');

var mkdirQ = Q.denodeify(temp.mkdir);
var writeFileQ = Q.denodeify(fs.writeFile);
var modelWriterPrefix = 'model_writer';
var INPUT_MODEL = 'inputModel';
var passthroughData = {
    product: {
        version: 2
    },
    'pass-through': {
        global: {
            'thirdparty_folder-env': '/home/stack/stage/thirdparty',
            'oo_admin_password-folder': 'unset',
            'lib_mysql_java_file_name': 'libmysql-java_5.1.32-1_all.deb',
            'ovftool_installer': '/home/stack/stage/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle',
            'install_env': 'legacy',
            'qpress_file_name': ''
        }
    }
};

var expandedPassThroughData = {
    global: {
        'thirdparty_folder-env': '/home/stack/stage/thirdparty',
        'oo_admin_password-folder': 'unset',
        'lib_mysql_java_file_name': 'libmysql-java_5.1.32-1_all.deb',
        'ovftool_installer': '/home/stack/stage/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle',
        'install_env': 'legacy',
        'qpress_file_name': '',
        'service-settings': {
            'cinder-backup': {},
            'cinder-fc-zone-manager': {},
            'cinder-volume': {
                DEFAULT: {
                    enabled_backends: 'f89d670d-96bb-4557-9a45-96e265f31501',
                },
                'f89d670d-96bb-4557-9a45-96e265f31501': {
                    rbd_cluster_name: 'ceph',
                    rbd_secret_uuid: '457eb676-33da-42ec-9a8c-9293d545c337',
                    rbd_ceph_conf: '/etc/ceph/ceph.conf',
                    volume_backend_name: 'ceph',
                    volume_driver: 'cinder.volume.drivers.rbd.RBDDriver',
                    rbd_pool: 'volumes',
                    rbd_user: 'cinder'
                }
            }
        }

    }
};


var moreExpandedPassThroughData = {
    global: {
        'thirdparty_folder-env': '/home/stack/stage/thirdparty',
        'oo_admin_password-folder': 'unset',
        'lib_mysql_java_file_name': 'libmysql-java_5.1.32-1_all.deb',
        'ovftool_installer': '/home/stack/stage/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle',
        'install_env': 'legacy',
        'qpress_file_name': '',
        'service-settings': {
            'cinder-backup': {},
            'cinder-fc-zone-manager': {},
            'cinder-volume': {
                DEFAULT: {
                    enabled_backends: 'f89d670d-96bb-4557-9a45-96e265f31501, 36d72708-b66b-4a42-80bc-7e4ddfbd91c5'
                },
                'f89d670d-96bb-4557-9a45-96e265f31501': {
                    rbd_cluster_name: 'ceph',
                    rbd_secret_uuid: '457eb676-33da-42ec-9a8c-9293d545c337',
                    rbd_ceph_conf: '/etc/ceph/ceph.conf',
                    volume_backend_name: 'ceph',
                    volume_driver: 'cinder.volume.drivers.rbd.RBDDriver',
                    rbd_pool: 'volumes',
                    rbd_user: 'cinder'
                },
                '36d72708-b66b-4a42-80bc-7e4ddfbd91c5': {
                    rbd_cluster_name: 'ceph',
                    rbd_secret_uuid: '457eb676-33da-42ec-9a8c-9293d545c337',
                    rbd_ceph_conf: '/etc/ceph/ceph.conf',
                    volume_backend_name: 'ceph',
                    volume_driver: 'cinder.volume.drivers.rbd.RBDDriver',
                    rbd_pool: 'volumes',
                    rbd_user: 'cinder'
                }
            }

        }
    }
};


function writePt() {
    return writeFileQ(path.join(midSizeExamplePath, 'data', 'passthrough.yml'),
        yaml.safeDump(passthroughData));
}

function writeAnotherPt() {
    var anotherPassthrough =
    {
        product: {
            version: 2
        },
        'pass-through': {
            global: {
                esx_cloud: true
            }
        }
    };

    return writeFileQ(path.join(midSizeExamplePath, 'data', 'legacy_passthrough.yml'),
        yaml.safeDump(anotherPassthrough));
}

function deletePassthrough() {
    fs.unlinkSync(path.join(midSizeExamplePath, 'data', 'passthrough.yml'));
    var anotherPt = path.join(midSizeExamplePath, 'data', 'legacy_passthrough.yml');
    if (fs.existsSync(anotherPt)) {
        fs.unlinkSync(anotherPt);
    }
}

describe('Single Passthrough file tests', function() {

    it('should write out template with no changes when a passthrough file is present', function(done) {

        mkdirQ(modelWriterPrefix + '_normal').then(function(dirPath) {
            return writePt()
                .then(function() {
                    // Normal case, no changes to template
                    console.log('Wrote normal model to: ' + dirPath);
                    return reader.readTemplate(midSizeExamplePath)
                        .then(_.partialRight(writeTemplate, dirPath));
                }).then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    done(fileContainingPassthroughData.length != 1);
                }).catch(done);

        });
    });

    it('should append incremental passthrough data to a single file', function(done) {

        mkdirQ(modelWriterPrefix + '_added_passthrough').then(function(dirPath) {
            console.log('Wrote normal model to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(data) {
                    // patch passthrough data
                    data[INPUT_MODEL]['pass-through'] = expandedPassThroughData;
                    return data;
                })
                .then(_.partialRight(writeTemplate, dirPath))
                .then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    done(fileContainingPassthroughData.length != 1);
                });
        }).catch(done);

    });


    it('should append incremental passthrough data to a single file', function(done) {

        mkdirQ(modelWriterPrefix + '_added_passthrough').then(function(dirPath) {
            console.log('Wrote normal model to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(data) {
                    // patch passthrough data
                    data[INPUT_MODEL]['pass-through'] = moreExpandedPassThroughData;
                    return data;
                })
                .then(_.partialRight(writeTemplate, dirPath))
                .then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    done(fileContainingPassthroughData.length != 1);
                });
        }).catch(done);

    });


    after(function(done) {
        deletePassthrough();
        exec('rm -rf /tmp/' + modelWriterPrefix + '*', done);
    });

});
describe('Multiple Passthrough file tests', function() {

    it('should write out template with no changes when a passthrough file is present', function(done) {

        mkdirQ(modelWriterPrefix + '_multi_normal').then(function(dirPath) {
            return writePt()
                .then(writeAnotherPt)
                .then(function() {
                    // Normal case, no changes to template
                    console.log('Wrote normal model to: ' + dirPath);
                    return reader.readTemplate(midSizeExamplePath)
                        .then(_.partialRight(writeTemplate, dirPath));
                }).then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    // there should be two pass-through files
                    done(fileContainingPassthroughData.length != 2);
                }).catch(done);

        });
    });

    it('should write incremental passthrough data to a new file', function(done) {

        mkdirQ(modelWriterPrefix + '_multi_added_passthrough').then(function(dirPath) {
            console.log('Wrote normal model to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(data) {
                    // patch passthrough data
                    data[INPUT_MODEL]['pass-through'] = expandedPassThroughData;
                    data[INPUT_MODEL]['pass-through'].global.esx_cloud = true;
                    return data;
                })
                .then(_.partialRight(writeTemplate, dirPath))
                .then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    done(fileContainingPassthroughData.length != 3);
                });
        }).catch(done);

    });


    it('should write incremental service-settings passthrough data to prev. file', function(done) {

        mkdirQ(modelWriterPrefix + '_multi_added_passthrough').then(function(dirPath) {
            console.log('Wrote normal model to: ' + dirPath);
            return reader.readTemplate(midSizeExamplePath)
                .then(function(data) {
                    // patch passthrough data     //Step 2
                    data[INPUT_MODEL]['pass-through'] = expandedPassThroughData;
                    data[INPUT_MODEL]['pass-through'].global.esx_cloud = true;
                    return data;
                })
                .then(_.partialRight(writeTemplate, dirPath))
                .then(_.partial(reader.readTemplate, dirPath))
                .then(function(data) {
                    // patch passthrough data     // Step 3
                    data[INPUT_MODEL]['pass-through'] = moreExpandedPassThroughData;
                    data[INPUT_MODEL]['pass-through'].global.esx_cloud = true;
                    return data;
                })
                .then(_.partialRight(writeTemplate, dirPath))
                .then(_.partial(reader.readTemplate, dirPath))
                .then(function(model) {
                    var fileContainingPassthroughData = model.fileInfo.sections['pass-through'];
                    done(fileContainingPassthroughData.length != 3);
                });
        }).catch(done);

    });


    after(function(done) {
        deletePassthrough();
        exec('rm -rf /tmp/' + modelWriterPrefix + '*', done);
    });

});

function writeTemplate(inputModel, path) {
    return modelWriter.writeModel(Object.assign({}, inputModel), path)
        .catch(function(err) {
            console.log('Failed to write file due to: ' + err);
        });
}
