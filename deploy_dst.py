#!/usr/bin/env python3
"""
Deploy DST configuration using Ansible.

Copyright (c) 2020 Joe Clarke <jclarke@cisco.com>

 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions
 are met:
 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

 THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
 ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
 FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 SUCH DAMAGE.

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
