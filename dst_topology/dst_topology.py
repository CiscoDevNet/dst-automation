from __future__ import print_function
from builtins import input
from builtins import range
from builtins import object
from virl2_client import ClientLibrary
import string
import random
import time
import os


class DSTTopology(object):
    __client = None
    __lab = None

    __started = False
    __wiped = True

    __base_config_dir = None

    __nodes = {
        "Internet Router": {"type": "iosv", "node": None, "config": "internet_router.txt"},
        "HQ Firewall": {"type": "asav", "node": None, "config": "hq_firewall.txt"},
        "HQ Switch": {"type": "unmanaged_switch", "node": None},
        "HQ Server": {"type": "ubuntu", "node": None, "config": "hq_server.txt"},
        "Internet": {"type": "external_connector", "node": None},
        "OOB Management": {"type": "external_connector", "node": None, "config": "oob_management.txt"},
    }

    def __init__(self, cml_controller, base_config_dir):
        self.__base_config_dir = base_config_dir

        ssl_cert = False

        if "CA_BUNDLE" in os.environ:
            ssl_cert = os.environ["CA_BUNDLE"]

        # Create a client and use the environment to provide the username, password, and CA bundle
        self.__client = ClientLibrary(cml_controller, ssl_verify=ssl_cert)

    @staticmethod
    def __get_lab_suffix():
        return "".join(random.choice(string.ascii_lowercase + string.digits) for i in range(8))

    def __create_lab(self):
        # Wait for the low-level drive to connect
        self.__client.wait_for_lld_connected()

        lab_prefix = "Dynamic Split Tunnel Test-"
        lab_suffix = DSTTopology.__get_lab_suffix()

        # Find a unique name for this lab
        while True:
            labs = self.__client.find_labs_by_title(lab_prefix + lab_suffix)
            if labs is not None and len(labs) > 0:
                lab_suffix = DSTTopology.__get_lab_suffix()
            else:
                break

        self.__lab = self.__client.create_lab(title=lab_prefix + lab_suffix)
        self.__lab.description = "This lab is for testing a Dynamic Split Tunnel config change (created at: {ctime})".format(
            ctime=time.ctime()
        )
        self.__lab.wait_for_convergence = False

    def __add_nodes(self):
        # Create each node
        for node in list(self.__nodes.keys()):
            self.__nodes[node]["node"] = self.__lab.create_node(node, self.__nodes[node]["type"], populate_interfaces=True)

    def __connect_nodes(self):
        """
        Connect all nodes in the test topology is a known, static way.
        """

        # First connect Gi0/0 of the Internet Router to the Internet
        igi0 = self.__nodes["Internet Router"]["node"].get_interface_by_label("GigabitEthernet0/0")
        iport = self.__nodes["Internet"]["node"].get_interface_by_label("port")
        self.__lab.create_link(igi0, iport)

        # Next connect Gi0/1 of the Internet Router to Gi0/0 of the HQ Firewall
        igi1 = self.__nodes["Internet Router"]["node"].get_interface_by_label("GigabitEthernet0/1")
        fgi0 = self.__nodes["HQ Firewall"]["node"].get_interface_by_label("GigabitEthernet0/0")
        self.__lab.create_link(igi1, fgi0)

        # Next connect Gi0/1 of the HQ Firewall to port0 of the HQ Switch
        # ...But before we can do that, we need to add a new interface.
        self.__nodes["HQ Firewall"]["node"].create_interface()
        fgi1 = self.__nodes["HQ Firewall"]["node"].get_interface_by_label("GigabitEthernet0/1")
        sport0 = self.__nodes["HQ Switch"]["node"].get_interface_by_label("port0")
        self.__lab.create_link(fgi1, sport0)

        # Next connect Management0/0 of HQ Firewall to the OOB Management network
        fm0 = self.__nodes["HQ Firewall"]["node"].get_interface_by_label("Management0/0")
        oport = self.__nodes["OOB Management"]["node"].get_interface_by_label("port")
        self.__lab.create_link(fm0, oport)

        # Next connect port1 of HQ Switch to port enp0s2 of the HQ Server
        sport1 = self.__nodes["HQ Switch"]["node"].get_interface_by_label("port1")
        seth = self.__nodes["HQ Server"]["node"].get_interface_by_label("enp0s2")
        self.__lab.create_link(sport1, seth)

    def __configure_nodes(self):
        for node, properties in list(self.__nodes.items()):
            if "config" in properties:
                config = self.__base_config_dir + "/" + properties["config"]
                if not os.path.exists(config):
                    raise FileNotFoundError(config)

                with open(config, "r") as fd:
                    conf_contents = fd.read()
                    properties["node"].config = conf_contents

    def create_topology(self):
        """
        Create a DST test topology and configure it.
        """

        self.__create_lab()
        self.__add_nodes()
        self.__connect_nodes()
        self.__configure_nodes()

    def start(self):
        """
        Start the DST test lab.
        """

        if self.__started:
            return

        self.__lab.start()
        self.__started = True
        self.__wiped = False

    def stop(self):
        """
        Stop the DST test lab.
        """

        if not self.__started:
            return

        self.__lab.stop(wait=True)
        self.__started = False

    def is_ready(self):
        """
        Check if the overall lab is ready.

        Returns:
            Boolean: True if all nodes have converged, False otherwise.
        """

        if not self.__started:
            raise Exception("Lab has not been started yet.")

        ready = True
        for node, properties in list(self.__nodes.items()):
            if not properties["node"].has_converged() or properties["node"].has_converged() == 0 or not properties["node"].is_booted():
                ready = False
                break

        return ready

    def get_fw_ip(self, wait=False):
        """
        Return the IP address of the OOB Management interface on the firewall node.

        Parameters:
            wait (Boolean): Whether or not to wait for the firewall node to converge (default: False)

        Returns:
            string: The first IP address on Management0/0 if found, else None
        """

        if not self.__started:
            raise Exception("Lab has not been started yet.")

        if not wait and not self.__nodes["HQ Firewall"]["node"].has_converged():
            raise Exception("Firewall node has not yet converged.")
        elif not self.__nodes["HQ Firewall"]["node"].has_converged():
            while not self.__nodes["HQ Firewall"]["node"].has_converged():
                time.sleep(1)

        fm0 = self.__nodes["HQ Firewall"]["node"].get_interface_by_label("Management0/0")
        ip4_addr = fm0.discovered_ipv4
        if len(ip4_addr) > 0:
            return ip4_addr[0]

        return None

    def wipe(self):
        """
        Wipe the DST test lab
        """

        if self.__started:
            raise Exception("Lab must be stopped first.")

        self.__lab.wipe(wait=True)
        self.__wiped = True

    def remove(self):
        """
        Remove the lab from the CML controller.
        """

        if not self.__wiped:
            raise Exception("Lab must be wiped before it can be removed.")

        self.__lab.remove()


if __name__ == "__main__":
    dstt = DSTTopology("192.168.10.229", "../base_configs")
    dstt.create_topology()
    dstt.start()
    while not dstt.is_ready():
        print("Waiting for topology to converge...")
        time.sleep(1)
    print("DONE.")

    print("Firewall IP: {}".format(dstt.get_fw_ip()))

    input("Hit Enter to remove the topology...")
    dstt.stop()
    dstt.wipe()
    dstt.remove()
