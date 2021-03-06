#!/bin/bash

##############################################################################
# Copyright (c) 2016 Huawei Technologies Co.,Ltd and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
##############################################################################

# StorPerf plugin un-installation script

set -e

docker stop storperf-yardstick
docker rm -f storperf-yardstick
docker rmi opnfv/storperf

rm -rf /tmp/storperf-yardstick
