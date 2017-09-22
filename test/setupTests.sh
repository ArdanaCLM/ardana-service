#!/usr/bin/env bash
#
# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
rm -rf test/temp
mkdir test/temp
pushd test
pushd temp

git clone git://git.suse.provo.cloud/ardana/ardana-input-model
cd ardana-input-model
git checkout master
cd ..

# Used for testing git operations
mkdir openstack
pushd openstack
mkdir ardana
mkdir examples
mkdir -p my_cloud/definition/

pushd my_cloud/definition
cp -r ../../../ardana-input-model/2.0/examples/entry-scale-kvm-vsa/* .
popd


git init
git checkout -b site
git add -A
git commit -m "site commit"
