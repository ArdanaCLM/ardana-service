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
var gulp = require('gulp'),
    istanbul = require('gulp-istanbul'),
    jasmine = require('gulp-jasmine'),
    reporters = require('jasmine-reporters'),
    path = require('path');

var rootDir = path.join(__dirname, '../');
var coverageFiles = [path.join(rootDir, 'lib/**/!(*.spec).js'), path.join(rootDir, 'api/**/!(*.spec).js')];
var testFiles = path.join(rootDir, 'test/**/*.spec.js');
var resultsDir = path.join(rootDir, 'test/.test-results');

gulp.task('pre-jasmine', function() {
    return gulp.src(coverageFiles)
        .pipe(istanbul())
        // Force `require` to return covered files
        .pipe(istanbul.hookRequire());
});

var error;

gulp.task('jasmine', ['pre-jasmine'], function(cb) {
    gulp.src(testFiles)
        .pipe(jasmine({
            reporter: [
                new reporters.TerminalReporter({
                    verbosity: 3,
                    showStack: true
                }),
                new reporters.JUnitXmlReporter({
                    savePath: path.join(resultsDir, 'jasmine')
                })
            ]
        }))
        .on('error', function(err) {
            // Store the error and continue
            error = err;
            // emit end will kick off istanbul (don't ask)
            this.emit('end');
        })
        .pipe(istanbul.writeReports({
            reporters: ['html', 'text-summary'],
            dir: path.join(resultsDir, 'coverage')
        })) // Creating the reports after tests ran
        .pipe(istanbul.enforceThresholds({
            thresholds: {
                global: {
                    statements: 0, // target 100
                    branches: 0, // target 100
                    functions: 0, // target 100
                    lines: 0 // target 100
                }
            }
        }))
        .on('error', function(err) {
            // Can only send one error, retain the more important jasmine one
            error = error || err;
        })
        .on('end', function(obj) {
            // Ensure we only call the callback ONCE with the correct error.
            cb(error);
        });
});

