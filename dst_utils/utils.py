"""
Utility functions for the DST automation use case.

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
from builtins import next
from builtins import object
import threading
import itertools
import time
import sys
import os
import tempfile
import json
import subprocess
from shutil import which
from yaml import load, dump

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

"""
This spinner code is taken from https://stackoverflow.com/questions/4995733/how-to-create-a-spinning-command-line-cursor
Contributed there by Victor Moyseenko and Tagar
"""


class Spinner(object):
    def __init__(self, message, delay=0.1):
        self.spinner = itertools.cycle(["-", "/", "|", "\\"])
        self.delay = delay
        self.busy = False
        self.spinner_visible = False
        sys.stdout.write(message)

    def write_next(self):
        with self._screen_lock:
            if not self.spinner_visible:
                sys.stdout.write(next(self.spinner))
                self.spinner_visible = True
                sys.stdout.flush()

    def remove_spinner(self, cleanup=False):
        with self._screen_lock:
            if self.spinner_visible:
                sys.stdout.write("\b")
                self.spinner_visible = False
                if cleanup:
                    sys.stdout.write(" ")  # overwrite spinner with blank
                    sys.stdout.write("\r")  # move to next line
                sys.stdout.flush()

    def spinner_task(self):
        while self.busy:
            self.write_next()
            time.sleep(self.delay)
            self.remove_spinner()

    def __enter__(self):
        if sys.stdout.isatty():
            self._screen_lock = threading.Lock()
            self.busy = True
            self.thread = threading.Thread(target=self.spinner_task)
            self.thread.start()

    def __exit__(self, exception, value, tb):
        if sys.stdout.isatty():
            self.busy = False
            self.remove_spinner(cleanup=True)
        else:
            sys.stdout.write("\r")


"""
End Spinner code from StackOverflow
"""


def run_ansible_command(playb, inv, avars, skip_tags=None):
    """
    Run Ansible with a given playbook and inventory

    Parameters:
        playb (string): The name of the playbook to run
        inv (file object): The file pointer containing the Ansible inventory
        avars (file object): The file pointer containing the Ansible variables
    """

    python_exe = get_python_interpreter()
    command = [
        "ansible-playbook",
        "-i",
        inv.name,
        "-e",
        "dst_variable_file={}".format(avars.name),
        "-e",
        "ansible_python_interpreter={}".format(python_exe),
        "ansible/{}".format(playb),
    ]

    if skip_tags:
        command += ["--skip-tags", skip_tags]

    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = ""

    for line in iter(p.stdout.readline, b""):
        result += line.decode("utf-8")

    p.wait()

    if p.returncode != 0:
        resd = json.loads(result)
        emsg = ""
        ehost = "Unknown Host"
        etask = "Unknown Task"
        found_failure = False
        for block in resd["plays"][0]["tasks"]:
            for host, properties in list(block["hosts"].items()):
                if "failed" in properties and properties["failed"]:
                    ehost = host
                    etask = block["task"]["name"]
                    if "msg" in properties:
                        emsg += properties["msg"] + "\n"
                    if "stdout" in properties:
                        emsg += "\n".join(properties["stdout"])
                    found_failure = True
                    break
            if found_failure:
                break

        raise Exception("Failed to run the Ansible playbook task '{}' on host {}: {}".format(etask, ehost, emsg))


def done(msg):
    """
    Print a message and the string DONE to say the step has been completed.

    Parameters:
        msg (string): The message to print before the word "DONE."
    """

    print(msg + "DONE.")


def cleanup(dstt=None, inv=None, avars=None):
    """
    Cleanup the various transient elements of a test and Ansible run.

    Parameters:
        dstt (DSTTopology): An optional DSTTopology object to cleanup.
        inv (file object): An optional file descriptor pointer to an Ansible inventory file to remove.
        avars (file object): An optional file descriptor pointer to an Ansible variable file to remove.
    """

    e = None

    msg = "Cleaning up..."
    with Spinner(msg):
        try:
            if dstt:
                dstt.stop()
                dstt.wipe()
                dstt.remove()
        except Exception as ce:
            e = ce

        try:
            if inv:
                if not inv.closed:
                    inv.close()
                os.remove(inv.name)
        except Exception as ce:
            e = ce

        try:
            if avars:
                if not avars.closed:
                    avars.close()
                os.remove(avars.name)
        except Exception as ce:
            e = ce

    if e:
        raise (e)

    done(msg)


def check_sections(type, config):
    """
    Check that the right sections appear in the YAML config file.

    Parameters:
        type (string): Either "test" or "production" to indicate the type of execution being run.
        config (dict): A dictionary representing the current config file.
    """
    for sec in (type, "dst"):
        if sec not in config:
            print("ERROR: Section '{}' not found in config file.".format(sec))
            sys.exit(1)


def check_vars(type, config):
    """
    Check that the right variables appear in the right config file sections.

    Parameters:
        type (string): Either "test" or "production" to indicate the type of execution being run.
        config (dict): A dictionary representing the current config file.
    """
    for var in ("custom_name", "domains"):
        if var not in config["dst"]:
            print("ERROR: Variable '{}' not defined in 'dst' section in config file.".format(var))
            sys.exit(1)

    for var in ("ansible_user", "ansible_password", "ansible_become_password", "group_policies"):
        if var not in config[type]:
            print("ERROR Variable '{}' not defined in '{}' section in config file.".format(var, type))
            sys.exit(1)


def get_python_interpreter():
    """
    Attempt to locate the current Python interpreter.

    Returns:
        string: The path to the current Python interpreter
    """

    python_exe = which("python")
    if not python_exe:
        python_exe = sys.executable

    return python_exe


def build_ansible_inventory(config=None, fw_ip=None):
    """
    Build a basic ini-style Ansible inventory file.

    Parameters:
        config (dict): Optional dictionary representing the current configuration file (used in production mode).
        fw_ip (string): Optional firewall IP address (used in test mode).

    Returns:
        file object: File descriptor of the file containing the Ansible inventory.
    """

    inv = tempfile.NamedTemporaryFile(mode="w", delete=False)
    if fw_ip:
        inv.write(fw_ip + "\n")
    else:
        if not config or "production" not in config or "firewalls" not in config["production"]:
            raise Exception("The configuration must include a production.firewalls section")

        for fw in config["production"]["firewalls"]:
            inv.write(fw + "\n")

    inv.close()

    return inv


def build_ansible_vars(config, type):
    """
    Build a temporary YAML file to hold all of the Ansible variables.

    Parameters:
        config (dict): Dictionary representing the current configuration file.
        type (string): Either "test" or "production" to indicate the type of execution being run.

    Returns:
        file object: File descriptor of the file containing the Ansible variables.
    """

    vard = {}
    for sec in (type, "dst"):
        # Merge all variables together into a flat structure
        vard = {**vard, **config[sec]}

    # Put the current working directory in the file as a base for subsequent operations.
    vard["dst_base_dir"] = os.getcwd()

    # Add static Ansible variables.
    vard["ansible_network_os"] = "asa"
    vard["ansible_become_method"] = "enable"
    vard["ansible_become"] = "yes"
    vard["ansible_connection"] = "network_cli"

    avars = tempfile.NamedTemporaryFile(mode="w", delete=False)
    dump(vard, avars, Dumper=Dumper)

    avars.close()

    return avars
