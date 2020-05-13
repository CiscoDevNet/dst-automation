#!/usr/bin/env python3
"""
Test Dynamic Split Tunneling configuration using Cisco Modeling Labs.

Copyright (c) 2020, Copyright (c) 2020, Cisco Systems, Inc. or its affiliates
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

from __future__ import print_function
from builtins import input
from dst_topology import DSTTopology
import argparse
import sys
import subprocess
from dst_utils import *
import time
import tempfile
import os
import re
from yaml import load, dump

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def run_traceroute(host):
    """
    Run ICMP traceroute and return a list of the first three hops.

    Parameters:
        host (string): Target host to which to traceroute.

    Returns:
        tuple: Tuple of the first three hops along the path.
    """

    command = ["traceroute", "-I", "-4", "-q", "1", "-n", "-m", "3", "-w", "1", host]

    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = ""

    for line in iter(p.stdout.readline, b""):
        result += line.decode("utf-8")

    p.wait()

    # Extract each hop IP from the traceroute output.
    m = re.findall(r"[123]\s+([\d\.\*]+)\s", result)

    return m


def main():
    dstt = None
    fw_ip = None
    conf = None
    args = None
    msg = None
    def_routing = None
    tests_passed = True

    parser = argparse.ArgumentParser(prog=sys.argv[0], description="Test a set of Dynamic Split Tunnel configs")
    parser.add_argument(
        "--config",
        "-c",
        metavar="<CONFIG FILE>",
        help="Path to the configuration file; default: config.yaml in the current directory",
        default="config.yaml",
    )
    parser.add_argument(
        "--base-config-dir",
        "-b",
        metavar="<BASE CONFIG DIR>",
        help="Path to the base set of virtual device configs; default: base_configs dir in the current directory",
        default="base_configs",
    )
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print("ERROR: Config file {} does not exist!".format(args.config))
        sys.exit(1)

    with open(args.config, "r") as fd:
        conf = load(fd, Loader=Loader)

    check_sections("test", conf)

    for var in ("host", "user", "pass"):
        if var not in conf["cml"]:
            print("ERROR: Variable '{}' not defined in the 'cml' section in the config file.".format(var))
            sys.exit(1)

    check_vars("test", conf)

    for var in ("local_hosts", "tunnel_hosts", "canary_host", "vpn_hop"):
        if var not in conf["test"]:
            print("ERROR: Variable '{}' not defined in the 'test' section in the config file.".format(var))
            sys.exit(1)

    if not re.match(r"[\d\.]", conf["test"]["canary_host"]):
        print("ERROR: The canary_host must be an IPv4 address.")
        sys.exit(1)

    os.environ["VIRL2_USER"] = conf["cml"]["user"]
    os.environ["VIRL2_PASS"] = conf["cml"]["pass"]

    try:
        dstt = DSTTopology(conf["cml"]["host"], base_config_dir=args.base_config_dir)
    except Exception as e:
        print("ERROR: Failed to connect to the CML controller at {}: {}".format(conf["cml"]["host"], e))
        sys.exit(1)

    msg = "Creating test topology..."

    try:
        with Spinner(msg):
            dstt.create_topology()
    except Exception as e:
        print("ERROR: Failed to create topology on {}: {}".format(conf["cml"]["host"], e))
        sys.exit(1)

    done(msg)
    msg = "Starting topology..."

    try:
        with Spinner(msg):
            dstt.start()
    except Exception as e:
        print("ERROR: Failed to start topology: {}".format(e))
        try:
            cleanup(dstt=dstt)
        except:
            pass

        sys.exit(1)

    done(msg)
    msg = "Waiting for topology to be ready..."

    try:
        with Spinner("Waiting for topology to be ready..."):
            while not dstt.is_ready():
                time.sleep(1)
    except Exception as e:
        print("ERROR: Failed to wait for topology to be ready: {}".format(e))
        try:
            cleanup(dstt=dstt)
        except:
            pass

        sys.exit(1)

    done(msg)

    try:
        fw_ip = dstt.get_fw_ip()
        if not fw_ip:
            if "firewall_ip" not in conf["test"]:
                print(
                    "ERROR: Unable to dynamically obtain the firewall IP and a static IP has not been defined in {}; define 'firewall_ip' in the 'test' section of {}".format(
                        args.config, args.config
                    )
                )
                try:
                    cleanup(dstt=dstt)
                except:
                    pass

                sys.exit(1)
            else:
                fw_ip = conf["test"]["firewall_ip"]
    except Exception as e:
        print("ERROR: Failed to obtain the firewall IP: {}".format(e))
        try:
            cleanup(dstt=dstt)
        except:
            pass

    command = ["ping", "-W", "1", "-c", "1", "-q", fw_ip]
    rc = 1
    msg = "Making sure HQ Firewall is reachable..."
    with Spinner(msg):
        while rc != 0:
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            p.wait()
            rc = p.returncode

    done(msg)

    inv = build_ansible_inventory(fw_ip=fw_ip)
    avars = build_ansible_vars(conf, "test")

    msg = "Running Ansible to provision the firewall for testing..."

    os.environ["ANSIBLE_CONFIG"] = os.getcwd() + "/ansible/dst.ansible.cfg"
    os.environ["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    with Spinner(msg):
        try:
            run_ansible_command("dst-playbook.yaml", inv, avars)
        except Exception as e:
            print("")
            print("ERROR: {}".format(e))
            try:
                cleanup(dstt=dstt, inv=inv, avars=avars)
            except:
                pass
            sys.exit(1)

    done(msg)

    msg = "Testing canary to get default routing..."
    with Spinner(msg):
        def_routing = run_traceroute(conf["test"]["canary_host"])

    done(msg)

    print("")
    while True:
        print("Dynamic Split Tunnel VPN is ready to test.")
        ans = input("Point AnyConnect to {} then when connected, hit 'y' and press Enter in this window to start the test...".format(fw_ip))
        if ans.lower().startswith("y"):
            break
    print("")

    msg = "Testing VPN tunneled hosts..."
    with Spinner(msg):
        if "hq_server_ip" in conf["test"]:
            # Append the internal host for testing.
            conf["test"]["tunnel_hosts"].append(conf["test"]["hq_server_ip"])

        print("")
        for host in conf["test"]["tunnel_hosts"]:
            imsg = "\tInspecting route to {}".format(host)
            rt = None
            with Spinner(imsg):
                rt = run_traceroute(host)
            bad = False
            if rt[2] != conf["test"]["vpn_hop"] and rt[2] != host:
                bad = True
                tests_passed = False

            if bad:
                sys.stdout.write(imsg + " [\033[33mWARNING\033[0m] Unexpected route: {}\n".format(", ".join(rt)))
            else:
                sys.stdout.write(imsg + " [\033[32mOK\033[0m] ({})\n".format(", ".join(rt)))

    done(msg)

    msg = "Testing Split Tunnel hosts..."
    with Spinner(msg):
        print("")
        for host in conf["test"]["local_hosts"]:
            imsg = "\tInspecting route to {}".format(host)
            rt = None
            with Spinner(imsg):
                rt = run_traceroute(host)
            i = 0
            bad = False
            for hop in rt:
                if rt[i] != def_routing[i]:
                    bad = True
                    tests_passed = False
                    break

                i += 1

            if bad:
                sys.stdout.write(imsg + " [\033[33mWARNING\033[0m] Unexpected route: {}\n".format(", ".join(rt)))
            else:
                sys.stdout.write(imsg + " [\033[32mOK\033[0m] ({})\n".format(", ".join(rt)))

    done(msg)

    # if not tests_passed:
    #     while True:
    #         ans = input("XXX: Hit 'y' and Enter to continue...")
    #         if ans.lower().startswith("y"):
    #             break

    msg = "Resetting the test topology..."

    with Spinner(msg):
        try:
            run_ansible_command("reset-test-playbook.yaml", inv, avars)
        except Exception as e:
            print("")
            print("WARNING: Failed to reset the topology config: {}".format(e))

    done(msg)

    try:
        cleanup(dstt=dstt, inv=inv, avars=avars)
    except Exception as e:
        print("")
        print("WARNING: Failed to cleanup after the test: {}".format(e))
        sys.exit(1)

    print("")
    if tests_passed:
        sys.stdout.write("All tests \033[32mPASSED\033[0m!\n")
    else:
        sys.stdout.write("One or more tests \033[31mFAILED\033[0m!\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
