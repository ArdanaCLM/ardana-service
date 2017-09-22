#!/bin/bash
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

# (use -w option to change)
LOCAL_WORKSPACE="${HOME}/dev"

# Remote paths on the deployer
ARDANA_PATH="/home/stack/openstack/"
TEMPLATE_PATH="/home/stack/ardana-ci/"
SCRATCH_PATH="/home/stack/scratch"
OPT_STACK_PATH="/opt/stack"

umount=false

# Defaults for Standard setup
DEPLOYER_IP="192.168.10.254"
DEPLOYER_SSH_PORT="22"

while getopts "b:w:i:p:ud" OPTION; do
    case "${OPTION:-}" in
        w)
            LOCAL_WORKSPACE="${OPTARG:-}" # remove trailing slash
            LOCAL_WORKSPACE="${LOCAL_WORKSPACE%/}" # remove trailing slash
            ;;
        u)
            # Un-mount all shares
            umount=true
            ;;
        d)
            # DeployerInCloud
            DEPLOYER_IP="192.168.245.2"
            ;;
        i)  DEPLOYER_IP="${OPTARG:-}"
            ;;
        p)  DEPLOYER_SSH_PORT="${OPTARG:-}"
            ;;
    esac
done

if [ "$umount" = true ] ; then
    echo "Unmounting all SSHFS shares..."
    sudo umount ${LOCAL_WORKSPACE}/openstack && echo "Successfully unmounted ${LOCAL_WORKSPACE}/openstack"
    sudo umount ${LOCAL_WORKSPACE}/scratch && echo "Successfully unmounted ${LOCAL_WORKSPACE}/scratch"
    sudo umount ${LOCAL_WORKSPACE}/ardana-ci && echo "Successfully unmounted ${LOCAL_WORKSPACE}/ardana-ci"
    sudo umount ${OPT_STACK_PATH} && echo "Successfully unmounted ${OPT_STACK_PATH}"
    exit 0
fi

echo -n "Making sure you have sshfs installed..."
sshfs --version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e " \033[31m[FAIL]\nRequired sshfs is not installed!\033[m"
    echo -e "\nTo install sshfs on Ubuntu, run:\n  \033[32msudo apt-get install sshfs\033[m"
    exit 1
else
    echo -e " \033[32m[OK]\033[m"
fi

echo -n "Making sure you we have password-less ssh access to the Deployer..."
ssh-keygen -R ${DEPLOYER_IP} > /dev/null 2>&1
ssh-keyscan -t rsa ${DEPLOYER_IP} -p ${DEPLOYER_SSH_PORT} >> ~/.ssh/known_hosts 2>/dev/null
sshpass -p "stack" ssh-copy-id stack@${DEPLOYER_IP} -p ${DEPLOYER_SSH_PORT} > /dev/null 2>&1
ret=$?
if [ $ret -ne 0 ]; then
    echo -e " \033[31m[FAIL]\nFailed to install our key. Make sure the Standard setup is up and the password is correct!\033[m"
    exit 1
else
    echo -e " \033[32m[OK]\033[m"
fi

# Mount openstack
echo "Mounting ${LOCAL_WORKSPACE}/openstack"
mkdir -p ${LOCAL_WORKSPACE}/openstack
sshfs -p ${DEPLOYER_SSH_PORT} stack@${DEPLOYER_IP}:${ARDANA_PATH} ${LOCAL_WORKSPACE}/openstack -o cache=no

# Mount scratch
echo "Mounting ${LOCAL_WORKSPACE}/scratch"
mkdir -p ${LOCAL_WORKSPACE}/scratch
sshfs -p ${DEPLOYER_SSH_PORT} stack@${DEPLOYER_IP}:${SCRATCH_PATH} ${LOCAL_WORKSPACE}/scratch -o cache=no

# Mount ardana-ci
echo "Mounting ${LOCAL_WORKSPACE}/ardana-ci"
mkdir -p ${LOCAL_WORKSPACE}/ardana-ci
sshfs -p ${DEPLOYER_SSH_PORT} stack@${DEPLOYER_IP}:${TEMPLATE_PATH} ${LOCAL_WORKSPACE}/ardana-ci

# Mount service venvs
echo "Mounting /opt/stack"
sudo mkdir -p /opt/stack
sudo chown ${USER}:${USER} /opt/stack
sshfs -p ${DEPLOYER_SSH_PORT} stack@${DEPLOYER_IP}:${OPT_STACK_PATH} ${OPT_STACK_PATH}

echo -e "\nAll done!"
