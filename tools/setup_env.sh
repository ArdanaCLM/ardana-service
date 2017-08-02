#!/bin/bash

# Gotta be somewhere in the tree to run this
git rev-parse || exit

cd $(git rev-parse --show-toplevel)

# Create dirs for customer data, scratch area
mkdir -p \
   data/my_cloud/model \
   data/my_cloud/config \
   data/scratch \
   log

cd data

for repo in hlm-input-model hlm-ansible ; do
    if [ ! -d $repo ] ; then
        git clone https://git.suse.provo.cloud/hp/$repo -b hp/prerelease/ocata
    fi
done
