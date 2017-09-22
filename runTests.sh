#!/bin/bash

npm install
test/setupTests.sh

# Update PATH
export PATH=${PWD}/node_modules/.bin:$PATH
gulp test
TEST_EXIT_CODE=$?
rm -rf temp
exit $TEST_EXIT_CODE

