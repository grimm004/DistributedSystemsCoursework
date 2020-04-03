from typing import List, Tuple
import Pyro4
import threading

REPLICA_PREFIX = "just_hungry.replica."


class ReplicationManager:
    def __init__(self, name_server: Pyro4.Proxy) -> None:
        self._ns: Pyro4.Proxy = name_server
        self._primary_replica: Pyro4.Proxy or None = None
        self._assigning_primary: bool = False
        self.assign_primary()

    def assign_primary(self):
        if not self._assigning_primary:
            print("Assigning a primary replica...")
            self._assigning_primary = True
            self._primary_replica = None
            primary_id: str = ""
            for replica_name, replica_uri in self._ns.list(prefix=REPLICA_PREFIX).items():
                replica_id = replica_name.replace(REPLICA_PREFIX, "")
                try:
                    proxy = Pyro4.Proxy(replica_uri)
                    if replica_id == proxy.id:
                        if self._primary_replica:
                            proxy.primary_id = primary_id
                        else:
                            self._primary_replica = proxy
                            self._primary_replica.primary_id = replica_id
                            primary_id = replica_id
                            print("Primary replica set to '%s'." % replica_id)
                    else:
                        print("Replica ID miss-match.")
                except Pyro4.errors.CommunicationError:
                    print("Could not connect to replica '%s'." % replica_id)
            if not self._primary_replica:
                print("Primary replica could not be set.")
            self._assigning_primary = False

    @Pyro4.expose
    @property
    def serving(self) -> bool:
        if not self._primary_replica:
            self.assign_primary()
        return bool(self._primary_replica)

    @Pyro4.expose
    def place_order(self, postcode: str, order: List[str], attempts: int = 1) -> Tuple[bool, str]:
        try:
            return self._primary_replica.place_order(postcode.replace(" ", "").lower(), order) \
                if self.serving else (False, "No longer serving.")
        except Pyro4.errors.CommunicationError:
            self.assign_primary()
            return self.place_order(postcode, order, attempts - 1)\
                if max(attempts, 0) else (False, "No longer serving.")

    @Pyro4.expose
    def get_orders(self, postcode: str, attempts: int = 1) -> Tuple[List[List[str]], str]:
        try:
            return self._primary_replica.get_orders(postcode.replace(" ", "").lower())\
                if self.serving else ([], "No longer serving.")
        except Pyro4.errors.CommunicationError:
            self.assign_primary()
            return self.get_orders(postcode, attempts - 1) if max(attempts, 0) else ([], "No longer serving.")

    @Pyro4.expose
    def register_replica(self, replica_id: str):
        try:
            if self._primary_replica:
                threading.Thread(target=lambda: self._primary_replica.new_replica(replica_id), daemon=True).start()
            else:
                threading.Thread(target=self.assign_primary, daemon=True).start()
        except Pyro4.errors.NamingError:
            print("Could not find new replica '%s'." % replica_id)
        except Pyro4.errors.CommunicationError:
            print("Communication error with new replica '%s'." % replica_id)


if __name__ == "__main__":
    import Pyro4.util
    import Pyro4.errors
    import sys

    sys.excepthook = Pyro4.util.excepthook


    def main() -> int:
        try:
            # Locate nameserver and create daemon server
            with Pyro4.locateNS() as ns, Pyro4.Daemon() as daemon:
                # Create replication manager instance and register it with daemon and nameserver
                manager: ReplicationManager = ReplicationManager(ns)
                manager_uri: Pyro4.URI = daemon.register(manager)
                ns.register("just_hungry.FrontEnd", manager_uri)

                print("Front end available.")
                daemon.requestLoop()
        except Pyro4.errors.NamingError:
            print("Failed to locate nameserver.")
            return 1
        else:
            return 0


    exit(main())
