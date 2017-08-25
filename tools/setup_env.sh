#!/bin/bash

# Gotta be somewhere in the tree to run this
git rev-parse || exit

cd $(git rev-parse --show-toplevel)

# Create dirs for customer data, scratch area
mkdir -p \
   data/my_cloud/model \
   data/my_cloud/config \
   data/scratch \
   data/cp/output \
   data/cp/ready \
   log

cd data

if [ ! -d my_cloud/.git ] ; then
    cd my_cloud
    git init 
    git add -A
    git commit -m "Initial commit"
    git checkout -b site
    cd -
fi

if [ ! -d hlm-ansible ] ; then
    git clone https://git.suse.provo.cloud/hp/hlm-ansible -b hp/prerelease/ocata
fi

if [ ! -d ardana-input-model ] ; then
    git clone https://git.suse.provo.cloud/ardana/ardana-input-model -b hp/opensource
fi

# Setup config processor.  This process basically automates the steps needed to
#    create a development environment for the config processor
if [ ! -d config-processor ] ; then
    if [ ! -f setup-hos-cp.sh ] ; then
        git clone https://git.suse.provo.cloud/hp/kenobi-configuration-processor -b hp/prerelease/ocata cp_temp
        sed -e 's/git.gozer.hpcloud.net/git.suse.provo.cloud/' -e 's#~/run_cp.sh#./run_cp.sh#' cp_temp/Scripts/setup-hos-cp.sh > setup-hos-cp.sh
        chmod +x ./setup-hos-cp.sh
        rm -rf cp_temp
    fi

    # Specify a directory for the config processor and the repos it needs
    DEST=config-processor

    # Prepare the dir for development, including checking out needed repos
    ./setup-hos-cp.sh -n $DEST

    # Prepare a virtual environment
    virtualenv -p /usr/bin/python2.7 $DEST
    VENV=$PWD/$DEST

    # Install pre-reqs into the virtual environment
    $VENV/bin/pip install -r $DEST/kenobi-configuration-processor/ConfigurationProcessor/requirements.txt

    # Install the config processor plugins into the python environment
    cd $DEST/kenobi-configuration-processor/ConfigurationProcessor
    $VENV/bin/python setup.py install
fi
