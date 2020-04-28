#!/usr/bin/env python3
"""
Deploy DST configuration using Ansible.

Copyright (c) 2020 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.

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


def main():
    conf = None
    args = None
    msg = None

    parser = argparse.ArgumentParser(prog=sys.argv[0], description="Deploy Dynamic Split Tunneling to a set of firewalls")
    parser.add_argument(
        "--config",
        "-c",
        metavar="<CONFIG FILE>",
        help="Path to the configuration file; default: config.yaml in the current directory",
        default="config.yaml",
    )
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print("ERROR: Config file {} does not exist!".format(args.config))
        sys.exit(1)

    with open(args.config, "r") as fd:
        conf = load(fd, Loader=Loader)

    check_sections("production", conf)
    check_vars("production", conf)

    inv = build_ansible_inventory(config=conf)
    avars = build_ansible_vars(conf, "production")

    msg = "Running Ansible to deploy DST config to production..."

    os.environ["ANSIBLE_CONFIG"] = os.getcwd() + "/ansible/dst.ansible.cfg"
    os.environ["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    with Spinner(msg):
        try:
            run_ansible_command("dst-playbook.yaml", inv, avars, skip_tags="test")
        except Exception as e:
            print("")
            print("ERROR: {}".format(e))
            try:
                cleanup(inv=inv, avars=avars)
            except:
                pass
            sys.exit(1)

    done(msg)

    try:
        cleanup(inv=inv, avars=avars)
    except Exception as e:
        print("")
        print("WARNING: Failed to cleanup after deployment: {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
