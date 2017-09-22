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
NODE_VERSION=v5.5.0
VERSION=$(sed -rn 's/.*"version".*"(.*)".*/\1/p' package.json)

# Get current git commit
COMMIT=$(git rev-parse HEAD)
SHORT_COMMIT_HASH=${COMMIT:0:8}

# Clean env
rm -rf node_modules

# Build tarball
mkdir ardana-service
wget -Nq http://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.gz -O nodejs.tar.gz
tar xzf nodejs.tar.gz -C ardana-service/

# Write out the version file
echo "v${VERSION} - git commit: ${COMMIT}" > ardana-service/.version

# Remove unnecessary content from node build
pushd ardana-service
mv node-${NODE_VERSION}-linux-x64 node
pushd node
for i in `ls | grep -v "bin\|include"`;
do
	rm -rf $i;
done
popd
popd

npm install --production

for i in api clouds config lib node_modules ansible
do
	cp -r $i ardana-service/$i
done

cp index.js ardana-service/index.js

pushd ardana-service
mkdir bin
pushd bin
ln -s ../node/bin/node
popd
tar -czvf ../ardana-service-${VERSION}-${SHORT_COMMIT_HASH}.tar.gz .
popd

# Clean
rm -rf nodejs.tar.gz
rm -rf ardana-service

type cowsay &> /dev/null
if [ $? -eq 0 ]; then
 cowsay -s 'All Done!'
else
 echo 'All Done!'
fi
