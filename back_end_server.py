import socket
import Pyro4
from Pyro4.util import SerializerBase
from http.client import HTTPConnection, HTTPResponse
from typing import List, Dict, Tuple, Any
import random
import json
import sys

REPLICA_PREFIX: str = "just_hungry.replica."


def http_get(request: str) -> HTTPResponse or None:
    try:
        if "//" in request:
            request = "//".join(request.split("//")[1:])
        [domain, *request_parts] = request.split("/")
        connection: HTTPConnection = HTTPConnection(domain)
        connection.request("GET", "/" + "/".join(request_parts))
        return connection.getresponse()
    except socket.error:
        print("socket.error")
        return


def verify_postcode(postcode: str) -> Tuple[bool, bool]:
    response: HTTPResponse or None = http_get("api.postcodes.io/postcodes/%s/validate" % postcode.strip()
                                              .replace(" ", ""))
    if response and response.status == 200:
        response_data: Dict[str, Any] = json.loads(response.readline())
        return True, response_data["status"] == 200 and response_data["result"]

    response: HTTPResponse or None = http_get("api.getthedata.com/postcode/%s" % postcode.strip()
                                              .replace(" ", ""))
    if response and response.status == 200:
        response_data: Dict[str, Any] = json.loads(response.readline())
        return True, response_data["status"] == "match"

    return False, False


@Pyro4.expose
@Pyro4.behavior("single")
class JustHungryReplica:
    def __init__(self, name_server: Pyro4.Proxy, rep_id: str,
                 orders: Dict[str, List[List[str]]] or None = None) -> None:
        self._ns: Pyro4.Proxy = name_server
        self._id: str = rep_id
        self._primary_id: str = ""
        self._orders: Dict[str, List[List[str]]] = orders if orders else {}

    def place_order(self, postcode: str, order: List[str]) -> Tuple[bool, str]:
        outcome, valid = verify_postcode(postcode)
        if outcome:
            if valid:
                if postcode not in self._orders:
                    self._orders[postcode] = []
                self._orders[postcode].append(order)
                self.update_states()
                return True, "#%d" % len(self._orders[postcode])
            else:
                return False, "Invalid postcode"
        return False, "Could not validate postcode"

    def get_orders(self, postcode: str) -> Tuple[List[List[str]], str]:
        if postcode in self._orders:
            return self._orders[postcode], ""
        return [], "Postcode not on record."

    def update_state(self, state: Dict[str, List[List[str]]]) -> None:
        self._orders = state

    def new_replica(self, replica_id) -> None:
        print("Updating state of new replica '%s'." % replica_id)
        replica_uri = self._ns.lookup(REPLICA_PREFIX + replica_id)
        replica: Pyro4.Proxy = Pyro4.Proxy(replica_uri)
        replica.update_state(self._orders)

    def update_states(self) -> None:
        for replica_name, replica_uri in self._ns.list(prefix=REPLICA_PREFIX).items():
            replica_id = replica_name.replace(REPLICA_PREFIX, "")
            if replica_id != self._id:
                try:
                    replica = Pyro4.Proxy(replica_uri)
                    replica.update_state(self._orders)
                    print("State of replica '%s' updated." % replica_id)
                except Pyro4.errors.CommunicationError:
                    print("Skipping unreachable replica '%s'." % replica_id)

    @property
    def id(self) -> str:
        return self._id

    @property
    def primary_id(self) -> str:
        return self._primary_id

    @primary_id.setter
    def primary_id(self, primary_id: str) -> None:
        self._primary_id = primary_id
        if self._primary_id == self._id:
            print("Allocated as primary server.")
            self.update_states()


if __name__ == "__main__":
    import string
    import Pyro4.errors
    import Pyro4.util
    import argparse

    sys.excepthook = Pyro4.util.excepthook

    arg_parser: argparse.ArgumentParser = argparse.ArgumentParser()
    arg_parser.add_argument("-i", "--id", type=str,
                            help="unique replica identification string (default: random)", default="")
    args = arg_parser.parse_args()


    def generate_id() -> str:
        return "".join(random.choices(list(string.ascii_letters + string.digits), k=20))


    def main() -> int:
        try:
            # Create daemon server, locate nameserver
            with Pyro4.Daemon() as daemon, Pyro4.locateNS() as ns:
                # Create a replica instance (with sample initial data)
                replica: JustHungryReplica = JustHungryReplica(ns, args.id if args.id else generate_id(), {
                    "dh13le": [["burger", "fries"], ["pizza"]],
                    "dh13lg": [["fried chicken", "chips"], ["vegetables"]]
                })
                # Register the new replica with the daemon server
                replica_uri: Pyro4.URI = daemon.register(replica)

                # Register replica with the nameserver
                ns.register(REPLICA_PREFIX + replica.id, replica_uri)

                # Register with front end server if available
                try:
                    print("Attempting to access front end server...")
                    front_end = Pyro4.Proxy(ns.lookup("just_hungry.FrontEnd"))
                    front_end.register_replica(replica.id)
                    print("Registered with FrontEnd")
                except Pyro4.errors.NamingError:
                    print("No front-end server found.")
                except Pyro4.errors.CommunicationError:
                    print("Communication error with front-end server.")

                print("Just Hungry replica '%s' available." % replica.id)
                daemon.requestLoop()
        except Pyro4.errors.NamingError as e:
            print(e)
            return 1
        except Pyro4.errors.CommunicationError as e:
            print(e)
        else:
            return 0


    exit(main())
