if __name__ == "__main__":
    from typing import List, Pattern
    import Pyro4
    import Pyro4.util
    import Pyro4.errors
    import sys
    import re

    # A simple postcode regex to check if an entry is roughly correct
    POSTCODE_REGEX: Pattern = re.compile(r"[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}", re.RegexFlag.IGNORECASE)

    sys.excepthook = Pyro4.util.excepthook


    def console_interface(just_hungry: Pyro4.Proxy) -> None:
        print("Welcome to Just Hungry!")

        postcode = ""
        while not POSTCODE_REGEX.match(postcode):
            postcode = input("Enter postcode to begin.\n > ")

        while True:
            print("\nCommands:\n" + "\n".join(["exit - Exit program",
                                               "order - Make order",
                                               "orders - View orders",
                                               "postcode - Change postcode"]))
            command = input("Please enter a command.\n > ").lower()
            if command == "exit":
                break
            elif command == "order":
                while True:
                    item_count_entry = input("Enter number of items to be ordered.\n > ")
                    if item_count_entry.isdigit():
                        item_count = int(item_count_entry)
                        break

                items: List[str] = []
                for i in range(item_count):
                    while True:
                        item = input("Input item #%s.\n > " % (i + 1))
                        if not item.isspace():
                            items.append(item.strip())
                            break

                outcome, comment = just_hungry.place_order(postcode, items)
                print(("Order %s successfully placed!" % comment)
                      if outcome else ("Could not place order: %s" % comment))
            elif command == "orders":
                orders, message = just_hungry.get_orders(postcode)
                if orders:
                    print("Orders:\n" + "\n".join(
                        ["#%d: %s" % (i + 1, ", ".join(orders[i])) for i in range(len(orders))]))
                else:
                    print(message if message else "No orders on record.")
            elif command == "postcode":
                postcode = ""
                while not POSTCODE_REGEX.match(postcode):
                    postcode = input("Enter postcode to begin.\n > ")
            elif command == "":
                pass
            else:
                print("Unrecognised command.")


    def main() -> int:
        try:
            # Try find and connect to the front-end server
            just_hungry = Pyro4.Proxy("PYRONAME:just_hungry.FrontEnd")
            if just_hungry.serving:
                console_interface(just_hungry)
            else:
                print("Just Hungry is not taking orders right now.")
        except Pyro4.errors.NamingError as e:
            if "unknown" in str(e):
                print("Could not find front-end server.")
            else:
                print("Error with nameserver:", e)
            return 1
        except Pyro4.errors.ConnectionClosedError:
            print("Connection closed.")
            return 1
        except Pyro4.errors.CommunicationError:
            print("Could not connect.")
            return 1
        else:
            return 0


    exit(main())
