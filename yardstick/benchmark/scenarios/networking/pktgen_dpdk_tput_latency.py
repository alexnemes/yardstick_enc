##############################################################################
# Copyright (c) 2016 ZTE corporation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
##############################################################################
from __future__ import absolute_import
import pkg_resources
import logging
import json
import time
import subprocess
import os

import yardstick.ssh as ssh
from yardstick.benchmark.scenarios import base

LOG = logging.getLogger(__name__)

class PktgenDPDKTputLatency(base.Scenario):
    """Execute pktgen-dpdk on one vm and execute testpmd on the other vm
    Determine transmit rate with loss within a given tolerance, then measure latency at that rate

  Parameters
    packetsize - packet size in bytes without the CRC
        type:    int
        unit:    bytes
        default: 64
    """
    __scenario_type__ = "PktgenDPDKTputLatency"

    PKTGEN_DPDK_LATENCY_SCRIPT = 'pktgen_dpdk_latency_benchmark.bash'
    PKTGEN_DPDK_TPUT_SCRIPT = 'pktgen_dpdk_tput_benchmark.bash'
    TESTPMD_SCRIPT = 'testpmd_fwd.bash'

    def __init__(self, scenario_cfg, context_cfg):
        self.scenario_cfg = scenario_cfg
        self.context_cfg = context_cfg
        self.setup_done = False

    def setup(self):
        """scenario setup"""
        self.pktgen_dpdk_latency_script = pkg_resources.resource_filename(
            'yardstick.benchmark.scenarios.networking',
            PktgenDPDKTputLatency.PKTGEN_DPDK_LATENCY_SCRIPT)
        self.pktgen_dpdk_tput_script = pkg_resources.resource_filename(
            'yardstick.benchmark.scenarios.networking',
            PktgenDPDKTputLatency.PKTGEN_DPDK_TPUT_SCRIPT)
        self.testpmd_script = pkg_resources.resource_filename(
            'yardstick.benchmark.scenarios.networking',
            PktgenDPDKTputLatency.TESTPMD_SCRIPT)

        host = self.context_cfg['host']
        target = self.context_cfg['target']
        LOG.info("user:%s, target:%s", target['user'], target['ip'])
        self.server = ssh.SSH.from_node(target, defaults={"user": "ubuntu"})
        self.server.wait(timeout=600)

        # copy script to host
        self.server._put_file_shell(self.testpmd_script, '~/testpmd_fwd.sh')

        LOG.info("user:%s, host:%s", host['user'], host['ip'])
        self.client = ssh.SSH.from_node(host, defaults={"user": "ubuntu"})
        self.client.wait(timeout=600)

        # copy script to host
        self.client._put_file_shell(
            self.pktgen_dpdk_tput_script, '~/pktgen_dpdk.sh')

        self.client._put_file_shell(
            self.pktgen_dpdk_latency_script, '~/pktgen_dpdk_latency.sh')

        LOG.info("Disabling Port Security")
        d = dict(os.environ)
        d['OS_AUTH_URL'] = "http://192.168.0.2:5000/"
        p = subprocess.Popen('openstack port list', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=d)
        for line in p.stdout.readlines():
            if "demeter" in line or "poseidon" in line:
                elements = line.split("|")
                port_id = elements[1].strip()
                LOG.debug("Checking port {} ".format(port_id))
                cmd = "openstack port show " + port_id + " | grep port_security_enabled"
                q = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=d)
                for line in q.stdout.readlines():
                    if line.split("|")[2].strip() == "True":
                        LOG.debug("Removing port security from port {}".format(port_id))
                        cmd = "neutron port-update " + port_id + " --no-security-groups"
                        q = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=d)
                        time.sleep(2)
                        cmd = "neutron port-update " + port_id + " --port_security_enabled=False"
                        q = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=d)
                        time.sleep(2)
                        LOG.debug(q.stdout.readlines())
                        if q.stderr:
                            LOG.debug(q.stderr.readlines())
                    else:
                        LOG.debug("Port security already disabled for this port. Doing nothing")

        LOG.info("Port Security Disabled for all test ports")

        self.setup_done = True
        self.testpmd_args = []
        self.pktgen_args = []

    @staticmethod
    def get_port_mac(sshclient, port):
        cmd = "ifconfig |grep HWaddr |grep %s |awk '{print $5}' " % port
        LOG.debug("Executing command: %s", cmd)
        status, stdout, stderr = sshclient.execute(cmd)

        if status:
            raise RuntimeError(stderr)
        else:
            return stdout.rstrip()

    @staticmethod
    def get_port_ip(sshclient, port):
        cmd = "ifconfig %s |grep 'inet addr' |awk '{print $2}' \
            |cut -d ':' -f2 " % port
        LOG.debug("Executing command: %s", cmd)
        status, stdout, stderr = sshclient.execute(cmd)

        if status:
            raise RuntimeError(stderr)
        else:
            return stdout.rstrip()

    @staticmethod
    def force_dhclient(sshclient, port):
        cmd = "sudo dhclient %s" % port
        LOG.debug("Executing command: %s", cmd)
        status, stdout, stderr = sshclient.execute(cmd)

        if status:
            raise RuntimeError(stderr)
        else:
            return stdout.rstrip()

    def run_iteration(self, testpmd_args, pktgen_args, packetsize, rate, duration, latency=False):
        iteration_result = {}
        LOG.debug("pktgen args: {}".format(pktgen_args))
        LOG.debug("testPMD args: {}".format(testpmd_args))

        cmd_pmd = "screen sudo -E bash ~/testpmd_fwd.sh %s %s %s %s %s" % \
                    (testpmd_args[0], testpmd_args[1], testpmd_args[2],
                    testpmd_args[3], testpmd_args[4])

        LOG.debug("testpmd command: {}".format(cmd_pmd))

        if latency:
            cmd_pktgen = "sudo -E bash ~/pktgen_dpdk_latency.sh %s %s %s %s %s %s %s %s %s" % \
                (pktgen_args[0], pktgen_args[1], pktgen_args[2],
                 pktgen_args[3], rate, packetsize,
                 pktgen_args[4], pktgen_args[5], duration)

        else:
            cmd_pktgen = "sudo -E bash ~/pktgen_dpdk.sh %s %s %s %s %s %s %s %s %s" % \
                (pktgen_args[0], pktgen_args[1], pktgen_args[2],
                 pktgen_args[3], rate, packetsize,
                 pktgen_args[4], pktgen_args[5], duration)

        LOG.debug("pktgen command: {}".format(cmd_pktgen))

        time.sleep(5)

        LOG.info("Executing command to start PMD: %s", cmd_pmd)
        self.server.send_command(cmd_pmd)
        #self.server.send_command(cmd)

        LOG.info("PMD launched")
        time.sleep(5)
        LOG.info("Launching PKTGEN")

        LOG.info("Executing command to start PKTGEN: %s", cmd_pktgen)
        status, stdout, stderr = self.client.execute(cmd_pktgen)

        LOG.debug("PKTGEN STatus : {}".format(status))
        LOG.debug("PKTGEN STDOUT : {}".format(stdout.strip()))
        LOG.debug("PKTGEN STDERR : {}".format(stderr))
        time.sleep(5)

        if status:
            # error cause in json dict on stdout
            raise RuntimeError(stdout)

        if not latency:
            result_output = "{" + stdout.strip().split("{")[1]
            iteration_result.update(json.loads(result_output))

        LOG.info("Stopping PMD Screen")
        time.sleep(2)

        cmd_pid="ps -eaf | grep SCREEN | grep -v grep | awk '{print $2}'"
        cmdpid_status, cmdpid_stdout, cmdpid_stderr = self.server.execute(cmd_pid)
        LOG.debug(cmdpid_stdout.strip())

        if cmdpid_stdout !=  "":
            cmd_kill="screen -S " + cmdpid_stdout.strip() + " -X stuff 'command'$(echo -ne \'\\015\')"
            LOG.debug("screen stop cmd : {}".format(cmd_kill))
            LOG.debug("killing screen PID - " + cmdpid_stdout.strip())
            cmdkill_status, cmdkill_stdout, cmdkill_stderr = self.server.execute(cmd_kill)
            time.sleep(2)
            cmdkill_status, cmdkill_stdout, cmdkill_stderr = self.server.execute(cmd_kill)

        if not latency:
            packets_per_second = iteration_result["packets_per_second"]
            bits_per_second = packets_per_second * 8 * (packetsize + 20)
            megabits_per_second = packets_per_second * 8 * (packetsize + 20) // 10**6
            iteration_result.update({"megabits_per_second": megabits_per_second})

            #for a 10Gbps line
            linerate_percentage = ( float(bits_per_second) / 10**10 ) * 100
            linerate_percentage = float("{0:.2f}".format(linerate_percentage))
            iteration_result.update({"linerate_percentage": linerate_percentage})

            loss_percentage = (iteration_result['packets_lost'] / float(iteration_result['packets_sent'])) * 100
            #take 5 decimals, to show packets lost per 10 million
            iteration_result.update({"loss_percentage": float("{0:.5f}".format(loss_percentage))})

            LOG.info("Iteration with rate {} result : {}".format(rate, iteration_result))

            # wait for finishing test
            time.sleep(1)

        if latency:

            cmd_latency_log = "cat ~/result_latency.log"
            latency_status, latency_stdout, latency_stderr = self.client.execute(cmd_latency_log)

            latency_output =  latency_stdout.encode('utf-8', 'ignore').decode('utf-8').split("Pktgen:/> page latency")

            latency_list=[]
            for elem in latency_output[0].split("[8;40H")[1:]:
                sample = int((elem.split("[9;40H")[0].split("\x1b")[0].strip()))
                if sample != 0:
                    latency_list.append(sample)

            if latency_status:
                raise RuntimeError(client_stderr)

            avg_latency = 0
            if latency_stdout:
                LOG.info("Latency list length : {}".format(len(latency_list)))
                LOG.info("Samples of latency: %s", latency_list)
                latency_sum = 0
                for i in latency_list:
                    latency_sum += int(i)
                avg_latency = latency_sum / len(latency_list)

            return {"avg_latency": avg_latency}

        return iteration_result

    def binary_search(self, testpmd_args, pktgen_args, packetsize, rate, loss_tolerance, duration):
        min_rate=0
        max_rate=rate
        iter_rate=max_rate

        while max_rate - min_rate > 0.5:

            LOG.info("Current iteration runs with rate: {} %".format(iter_rate))
            framesize_result = self.run_iteration(testpmd_args, pktgen_args, packetsize, iter_rate, duration)

            if framesize_result['loss_percentage'] > loss_tolerance:
                LOG.info("Loss {} > Tolerance {}, going down".format(framesize_result['loss_percentage'], loss_tolerance))
                max_rate = iter_rate
                iter_rate = ( max_rate + min_rate ) / 2.0

                LOG.info("Min rate : {} %, Max_rate : {} %".format(min_rate, max_rate))

            elif framesize_result['loss_percentage'] <= loss_tolerance:
                LOG.info("Loss {} <= Tolerance {}, going up".format(framesize_result['loss_percentage'], loss_tolerance))

                min_rate = iter_rate
                iter_rate = ( max_rate + min_rate ) / 2.0
                LOG.info("Min rate : {} %, Max_rate : {} %".format(min_rate, max_rate))

                res = framesize_result #last iteration result with loss within tolerance is the temporary result
        LOG.info("Finished iterating for frame size: {}".format(packetsize))
        return res


    def run(self, result):
        """execute the benchmark"""

        if not self.setup_done:
            self.setup()

        #sometimes the test instances start without IP addresses on test interfaces
        self.force_dhclient(self.client, 'ens4')
        self.force_dhclient(self.client, 'ens5')
        self.force_dhclient(self.server, 'ens4')
        self.force_dhclient(self.server, 'ens5')

        if not self.testpmd_args:
            client_src_ip = self.get_port_ip(self.client, 'ens4')
            client_dst_ip = self.get_port_ip(self.client, 'ens5')
            server_ens4_ip = self.get_port_ip(self.server, 'ens4')
            server_ens5_ip = self.get_port_ip(self.server, 'ens5')
            self.testpmd_args = [self.get_port_mac(self.client, 'ens5'),
                                    client_src_ip, client_dst_ip,
                                    server_ens4_ip, server_ens5_ip]

        if not self.pktgen_args:
            server_rev_mac = self.get_port_mac(self.server, 'ens4')
            server_send_mac = self.get_port_mac(self.server, 'ens5')
            client_src_ip = self.get_port_ip(self.client, 'ens4')
            client_dst_ip = self.get_port_ip(self.client, 'ens5')
            client_ens4_ip = client_src_ip
            client_ens5_ip = client_dst_ip
            self.pktgen_args = [client_src_ip, client_dst_ip,
                                server_rev_mac, server_send_mac,
                                client_ens4_ip, client_ens5_ip]

        LOG.debug("class pktgen args: {}".format(self.pktgen_args))
        LOG.debug("class testPMD args: {}".format(self.testpmd_args))

        options = self.scenario_cfg['options']
        packetsize = options.get("packetsize", 64)
        rate = options.get("rate", 100)
        loss_tolerance = options.get("loss_tolerance", 0.05)
        duration = options.get("duration", 30)

        LOG.info("Running throughput measurements for frame size {}".format(packetsize))

        result.update(self.binary_search(self.testpmd_args, self.pktgen_args, packetsize, rate, loss_tolerance,duration))

        LOG.info("Running latency measurements for frame size {} with rate {} %".format(packetsize, result['linerate_percentage']))

        result.update(self.run_iteration(self.testpmd_args, self.pktgen_args, packetsize, result['linerate_percentage'], duration, latency=True))

        LOG.info("Frame Size {} result with latency : {}".format(packetsize, result))

        avg_latency = result['avg_latency']

        if avg_latency and "sla" in self.scenario_cfg:
            sla_max_latency = int(self.scenario_cfg["sla"]["max_latency"])
            LOG.info("Average Latency : %d ", avg_latency)
            LOG.info("sla_max_latency: %d", sla_max_latency)
            debug_info = "avg_latency %d > sla_max_latency %d" \
                % (avg_latency, sla_max_latency)
            assert avg_latency <= sla_max_latency, debug_info