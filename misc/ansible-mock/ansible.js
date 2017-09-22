/**
 * (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
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
var stream = require('stream');
var fs = require('fs');
var lineSleeper = new stream.Transform();
var _ = require('lodash');
var sleep = require('sleep');
var logsMap = require('./logs-map');

var rx = /\$\$(\d+):/;

var lastOffset = 0;

// Allow the logfile replay speed to be changed to speed up the replaying of log files
var replaySpeed = process.env.MOCK_REPLAY_SPEED;
if (!replaySpeed) {
    replaySpeed = 1.0;
} else {
    replaySpeed = parseFloat(replaySpeed);
}

lineSleeper._transform = function(chunk, encoding, done) {
    var data = chunk.toString();

    var lines = data.split('\n');
    var that = this;
    _.each(lines, function(line) {
        var arr = rx.exec(line);
        if (_.isNull(arr)) {
            return that.push(line);
        }
        var offset = _.floor((arr[1] - lastOffset) * 1000);
        lastOffset = arr[1];
        var sleepTime = offset * replaySpeed;
        if (sleepTime <1) {
            sleepTime = 1;
        }
        sleep.usleep(sleepTime);
        var text = line.replace(arr[0], '');
        that._transform(text, encoding, _.noop);
    });
    done();
};

function getAnsiblePlaybookName() {
    var playbookName;
    var rx = /(\D*).yml/;
    _.each(process.argv, function(arg) {
        var arr = rx.exec(arg);
        if (!_.isNull(arr)) {
            playbookName = arr[1];
        }
    });
    return playbookName;
}
var source = fs.createReadStream(logsMap[getAnsiblePlaybookName()]);
source.pipe(lineSleeper);
lineSleeper.on('readable', function() {
    var line;
    while (null !== (line = lineSleeper.read())) {
        console.log(line.toString());
    }
});

process.on('exit', function() {
    var exitCode = process.env['NODE_TESTING_EXIT_CODE'] || 0;
    process.exit(exitCode);
});
