#!/bin/bash
# (c) Copyright 2017-2018 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Gotta be somewhere in the tree to run this
git rev-parse || exit

cd $(git rev-parse --show-toplevel)

GIT_BASE=${GIT_BASE:-git://git.suse.provo.cloud/ardana}

# Create dirs for customer data, scratch area
mkdir -p \
   data/my_cloud/model \
   data/my_cloud/config \
   data/scratch \
   data/cp/output \
   data/cp/ready \
   data/cp/internal \
   log

cd data

if [ ! -d my_cloud/.git ] ; then
    cd my_cloud
    git init
    git config commit.gpgsign false
    git commit --allow-empty -m "Initial commit"
    git checkout -b site
    cd -
fi

config_repos="cinder heat keystone neutron nova"
for repo in $config_repos ; do
    if [ ! -d ${repo}-ansible ]; then
        git clone ${GIT_BASE}/${repo}-ansible
    fi
    mkdir -p my_cloud/config/$repo
    cd ${repo}-ansible
    git ls-files | grep j2$ | xargs -I@ ln -fs ${PWD}/@ ../my_cloud/config/$repo
    cd -
done

if [ ! -d ardana-ansible ] ; then
    git clone ${GIT_BASE}/ardana-ansible
    touch ardana-ansible/keystone-status.yml
fi

if [ ! -d ardana-input-model ] ; then
    git clone ${GIT_BASE}/ardana-input-model
fi

# Specify a directory for the config processor and the repos it needs
DEST=config-processor
acp=ardana-configuration-processor

# Setup config processor.  This process basically automates the steps needed to
#    create a development environment for the config processor
if [ ! -d $DEST ] ; then
    mkdir $DEST

    git clone ${GIT_BASE}/$acp $DEST/$acp

    # Prepare the dir for development, including checking out needed repos
    $DEST/$acp/Scripts/setup-ardana-cp.sh -n $DEST

    # Prepare a virtual environment
    virtualenv -p /usr/bin/python2.7 $DEST
    VENV=$PWD/$DEST

    # upgrade the local version of pip in case the venv installed an old one
    $VENV/bin/pip install --upgrade pip

    # upgrade the local version of setuptools in case the venv installed an old one
    $VENV/bin/pip install --upgrade setuptools

    # Install the config processor plugins into the python environment
    cd $DEST/$acp
    $VENV/bin/python setup.py sdist
    $VENV/bin/pip install dist/ardana-configurationprocessor-*.tar.gz
    $VENV/bin/pip install jsonschema==2.6.0
fi

