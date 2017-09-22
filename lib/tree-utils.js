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
var path = require('path');
var Q = require('q');
var readdirQ = Q.denodeify(fs.readdir);
var statQ = Q.denodeify(fs.stat);

/**
 * Normalise passed string for use in REST routes.
 * 1. the string is lower-cased
 * 2. dashes '-' and dots '.' are replaced with underscores '_'
 * */
function normaliseName(name) {
    var ret = name;
    ret = ret.toLowerCase();
    ret = ret.replace(/(?:-|\.)/g, '_');
    return ret;
}

/**
 * Is the passed Object one of our leaf nodes?
 * */
function isLeaf(obj) {
    if (!_.isPlainObject(obj)) {
        return false;
    }
    return obj.hasOwnProperty('_path_') && obj.hasOwnProperty('_mtime_');
}

/**
 * Replace the value of leaf nodes with null
 * @return {Object} a new Tree identical to tree where leaf nodes have been null terminated
 * */
function nullTerminateLeaves(tree) {
    if (!_.isPlainObject(tree)) {
        return tree;
    }
    var ret = {};
    _.forEach(tree, function(val, key) {
        if (isLeaf(val)) {
            ret[key] = null;
        } else {
            ret[key] = nullTerminateLeaves(val);
        }
    });
    return ret;
}

/**
 * Parse a REST URL path into a lodash path
 * @param {string} originalPath a dash separated path
 * @return {string} a lodash-like version of originalPath
 * */
function urlToLodashPath(originalPath) {
    var matchedPath = normaliseName(originalPath);
    matchedPath = matchedPath.replace(/\//g, '.');
    if (matchedPath === '.') {
        matchedPath = '';
    }
    return matchedPath;
}

/**
 * Get a subtree by path
 * @param {string} subtreePath the path of the subtree to extract
 * @param {Object} tree the tree to extract a subtree from
 * */
function getRelevantSubtree(subtreePath, tree) {
    var lodashPath = urlToLodashPath(subtreePath);
    var subTree;
    if (!lodashPath) {
        subTree = tree;
    } else {
        subTree = _.get(tree, lodashPath);
    }
    if (!subTree) {
        throw {
            isUserError: 'Path not found in cp_output tree: ' + subtreePath,
            statusCode: 404
        };
    }
    return subTree;
}

/**
 * Recursively scan the passed directory into an Object tree
 * Leaves (files) are indicated with having an _mtime_ and _path_ property
 * All paths are normalised for use in REST routes
 * @param {string} dirPath the path of the directory to scan
 * @param {Object=} root optional Object to populate
 * @return {Object} a promise resolved when the directory is fully scanned
 * */
function scanDirectory(dirPath, root) {
    if (!root) {
        root = {};
    }
    return readdirQ(dirPath).then(function(files) {
        var promises = [];
        _.forEach(files, function(file) {
            var filePath = path.join(dirPath, file);
            var key = normaliseName(file);
            var promise = statQ(filePath).then(function(stats) {
                if (stats.isDirectory()) {
                    root[key] = {};
                    return scanDirectory(filePath, root[key]);
                }
                root[key] = {
                    _mtime_: stats.mtime,
                    _path_: filePath
                };
            });
            promises.push(promise);
        });
        return Q.all(promises).then(function() {
            return root;
        });
    });
}

exports.scanDirectory = scanDirectory;
exports.isLeaf = isLeaf;
exports.nullTerminateLeaves = nullTerminateLeaves;
exports.getRelevantSubtree = getRelevantSubtree;
