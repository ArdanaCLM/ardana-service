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
    mocha = require('gulp-mocha'),
    reporters = require('jasmine-reporters'),
    path = require('path'),
    exec = require('child_process').exec;

var rootDir = path.join(__dirname, '../');
var resultsDir = path.join(rootDir, 'coverage-report');


gulp.task('pre-test', function() {
    return gulp.src(['lib/*.js', 'api/*.js', 'config/*.js'])
        // Covering files
        .pipe(istanbul())
        // Force `require` to return covered files
        .pipe(istanbul.hookRequire());
});


gulp.task('mocha-unit-tests', ['pre-test'], function() {

    gulp.src('test/unit-tests/**/*.js')
        .pipe(istanbul())
        .pipe(mocha({
            reporter: 'min'
        })).pipe(istanbul.writeReports({
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
        }));
});
