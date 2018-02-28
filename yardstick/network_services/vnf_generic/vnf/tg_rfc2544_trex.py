# Copyright (c) 2016-2017 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Trex traffic generation definitions which implements rfc2544 """

from __future__ import absolute_import
from __future__ import print_function
import time
import logging
from collections import Mapping

from yardstick.network_services.vnf_generic.vnf.tg_trex import TrexTrafficGen
from yardstick.network_services.vnf_generic.vnf.sample_vnf import Rfc2544ResourceHelper
from yardstick.network_services.vnf_generic.vnf.tg_trex import TrexResourceHelper

LOGGING = logging.getLogger(__name__)


class TrexRfc2544ResourceHelper(Rfc2544ResourceHelper):

    def is_done(self):
        return self.latency and self.iteration.value > 10


class TrexRfcResourceHelper(TrexResourceHelper):

    LATENCY_TIME_SLEEP = 120
    RUN_DURATION = 30
    WAIT_TIME = 3

    def __init__(self, setup_helper, rfc_helper_type=None):
        super(TrexRfcResourceHelper, self).__init__(setup_helper)

        if rfc_helper_type is None:
            rfc_helper_type = TrexRfc2544ResourceHelper

        self.rfc2544_helper = rfc_helper_type(self.scenario_helper)

    def _run_traffic_once(self, traffic_profile):
        if self._terminated.value:
            return

        traffic_profile.execute_traffic(self)
        self.client_started.value = 1
        time.sleep(self.RUN_DURATION)
        self.client.stop(traffic_profile.ports)
        time.sleep(self.WAIT_TIME)
        samples = traffic_profile.get_drop_percentage(self)
        self._queue.put(samples)

        if not self.rfc2544_helper.is_done():
            return

        self.client.stop(traffic_profile.ports)
        self.client.reset(ports=traffic_profile.ports)
        self.client.remove_all_streams(traffic_profile.ports)
        traffic_profile.execute_traffic_latency(samples=samples)
        multiplier = traffic_profile.calculate_pps(samples)[1]
        for _ in range(5):
            time.sleep(self.LATENCY_TIME_SLEEP)
            self.client.stop(traffic_profile.ports)
            time.sleep(self.WAIT_TIME)
            last_res = self.client.get_stats(traffic_profile.ports)
            if not isinstance(last_res, Mapping):
                self._terminated.value = 1
                continue
            self.generate_samples(traffic_profile.ports, 'latency', {})
            self._queue.put(samples)
            self.client.start(mult=str(multiplier),
                              ports=traffic_profile.ports,
                              duration=120, force=True)

    def start_client(self, ports, mult=None, duration=None, force=True):
        self.client.start(ports=ports, mult=mult, duration=duration, force=force)

    def clear_client_stats(self, ports):
        self.client.clear_stats(ports=ports)

    def collect_kpi(self):
        self.rfc2544_helper.iteration.value += 1
        return super(TrexRfcResourceHelper, self).collect_kpi()


class TrexTrafficGenRFC(TrexTrafficGen):
    """
    This class handles mapping traffic profile and generating
    traffic for rfc2544 testcase.
    """

    def __init__(self, name, vnfd, setup_env_helper_type=None, resource_helper_type=None):
        if resource_helper_type is None:
            resource_helper_type = TrexRfcResourceHelper

        super(TrexTrafficGenRFC, self).__init__(name, vnfd, setup_env_helper_type,
                                                resource_helper_type)
