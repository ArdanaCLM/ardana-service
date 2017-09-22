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
ARDANA_DEV_TOOLS_SCRATCH_PATH=${HOME}/workspace/ardana-dev-tools/scratch-hp_opensource
PROJECT_NAME="ardana-service"
TARBALL_GOZER="http://hos.suse.provo.cloud/ardana-installer-ui"
PATCH_STANDARD=0
RED_COLOR=\\e[31m
GREEN_COLOR=\\e[92m
COLOR_END=\\e[0m
DEPLOYER_IP="192.168.10.254"

while getopts "s:p:cd" OPTION; do
	case "${OPTION:-}" in
		s)
			ARDANA_DEV_TOOLS_SCRATCH_PATH="${OPTARG:-}/ardana-dev-tools/scratch-hp_opensource"
			;;
		p)
			PROJECT_NAME="${OPTARG:-}"
			;;
		c)
			PATCH_STANDARD=1;
			;;
		d)
			DEPLOYER_IP="192.168.245.2"
	esac
done

function buildVenvPackage {
	for i in bin lib etc META-INF; do
		mkdir ${PREFIX}/$i;
	done

	cp *.tar.gz $PREFIX/lib

	for i in '' '2.7'; do
		for j in pip python; do
			ln -s $j$i $PREFIX/bin/$j$i;
		done
	done
}


function writeManifest {
	MANIFEST_PATH=$PREFIX/META-INF/$PROJECT_NAME.manifest-$TIMESTAMP

    # create dummy manifest file
	cat > $MANIFEST_PATH <<EOF
# Manifest for: ${PROJECT_NAME}
---

# Ardana environment
environment:
  distributor_id: debian
  description: "linux (cattleprod)"
  release: 8
  codename: cattleprod
  deployer_version: ardana-0.9.0
  pip_mirror: "redacted"
  hlinux_baseline:
    archive: hLinuxArchive/2017/openstack4.0.3_ga-2/
    codename: cattleprod
    dists: [main, contrib, non-free]
    mirror: "redacted"

# Git source SHA1(s)
git:
  - name: ardana-dev-tools
    branch: master
    url: git://git.suse.provo.cloud/ardana/ardana-dev-tools
    sha1: f5143309f63863d7f38990c7740f2932a1783c72

constraints:
  - repo: git://git.suse.provo.cloud/openstack/requirements
    tag: 35ab29214d4b6b04c1520dde09f978be40a14d8a

# External files
external: |
  acb2ed5e66b18fc5152e3fa8e5c3bd0f "redacted"

EOF
}

function updateTarball {
	TARBALL_NAME=$PROJECT_NAME-$TIMESTAMP.tgz
	cd ${PREFIX}
	tar acf ../$TARBALL_NAME *
	cd ..

	# Clean any existing project tarballs from scratch path
	rm -f $ARDANA_DEV_TOOLS_SCRATCH_PATH/$PROJECT_NAME*

	cp $TARBALL_NAME  $ARDANA_DEV_TOOLS_SCRATCH_PATH
	cp $MANIFEST_PATH $ARDANA_DEV_TOOLS_SCRATCH_PATH/

}

function patchDeployer {
	# delete existing
	ssh stack@${DEPLOYER_IP} "sudo rm -f /opt/ardana_packager/${PROJECT_NAME}*"
	ssh stack@${DEPLOYER_IP} "sudo rm -rf /opt/stack/venv/${PROJECT_NAME}*"
	ssh stack@${DEPLOYER_IP} "sudo rm -rf /opt/stack/service/${PROJECT_NAME}*"
	# extract existing timestamp from /opt/ardana_packager/packages
	CURRENT_HASH=$(ssh stack@${DEPLOYER_IP} "egrep -o $PROJECT_NAME-.* /opt/ardana_packager/packages | egrep -o [0-9]+T[0-9]+Z")

	if [ -z "$CURRENT_HASH" ]; then
	  echo -e "${RED_COLOR}Looks like your Standard setup wasn't brought up with a venv of this package! Please manually edit /opt/ardana_packager/packages!"
	  echo -e "Add the following entry in alphabetical order:
		$PROJECT_NAME:
			$TIMESTAMP: {file: $PROJECT_NAME-$TIMESTAMP.tgz}${COLOR_END}"
       exit 1
	fi
	# upload new one
	scp -q $TARBALL_NAME stack@${DEPLOYER_IP}:
	# move tarball to /opt/ardana_packager
	ssh stack@${DEPLOYER_IP} "sudo cp $TARBALL_NAME /opt/ardana_packager/"
	# patch packages file
	ssh stack@${DEPLOYER_IP} "sudo sed -i \"s/${CURRENT_HASH}/${TIMESTAMP}/g\" /opt/ardana_packager/packages"
}


function sanityCheck {

if [ ! -f *.tar.gz ]; then
  echo "${RED_COLOR}No tarball package exists for $PROJECT_NAME! Please run buildPackage.sh/make${COLOR_END}"
  exit 1
fi

if [ $PATCH_STANDARD -eq 1 ]; then
	sshpass -p "stack" ssh-copy-id stack@${DEPLOYER_IP} > /dev/null 2>&1
	if [ $? -ne 0 ]; then
		echo -e " ${RED_COLOR}Failed to install our key. Make sure standard config is up and the password is correct!${COLOR_END}"
		exit 1
	fi
fi

}

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
PREFIX="tmp-${TIMESTAMP}"
mkdir $PREFIX

echo -e "${GREEN_COLOR}Sanity checking your environment...${COLOR_END}"
sanityCheck

echo -e "${GREEN_COLOR}Looks good! Building venv package...${COLOR_END}"
# Build Venv package
buildVenvPackage

echo -e "${GREEN_COLOR}Done! Writing manifest file...${COLOR_END}"
# Write Manifest file
writeManifest

# TODO  patch venv_build.yml
# updateVenvBuild

echo -e "${GREEN_COLOR}Done! Creating tarball and patching local scratch${COLOR_END}"
# Create and update tarball in scratch
updateTarball

# If PATCH_STANDARD is set than the projects' packages from /opt/ardana_packager will be removed from the deployer.
# This does not need to be run if a new instance of standard config is being instantiated
if [ $PATCH_STANDARD -eq 1 ]; then
echo -e "${GREEN_COLOR}Patching Deployer...${COLOR_END}"
	patchDeployer
fi

rm -rf $PREFIX

echo -e "${GREEN_COLOR}All done!${COLOR_END}"
