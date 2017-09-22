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
    wrench = require('wrench');

console.log('Discovering Gulp files');
wrench.readdirSyncRecursive('./gulp').filter(function(file) {
    // Skip plugins directory
    if (/^plugins(\/|\\)/.test(file)) {
        return false;
    }
    return (/\.(js|coffee)$/i).test(file);
}).map(function(file) {
    console.log('Requiring: ' + file);
    require('./gulp/' + file);
});
console.log('Gulp file discovery finished');

// Collection of top level targets
gulp.task('test', ['lint', 'mocha-unit-tests']);
gulp.task('default', ['nodemon']);
