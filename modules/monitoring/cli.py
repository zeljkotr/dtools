"""
modules/monitoring/cli.py

CLI interfejs za monitoring modul. Sva logika (baza, provere) je u core.py -
ovaj fajl samo prikazuje meni i poziva core funkcije.
"""

from . import core


class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _prompt(text, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{text}{suffix}: ").strip()
    return val if val else default


def menu_add_target():
    print(f"\n{C.BOLD}--- Dodaj target ---{C.RESET}")
    print("Kategorija:")
    for k, v in core.CATEGORIES.items():
        print(f"  {k}. {v}")
    cat = input("Izbor: ").strip()
    if cat not in core.CATEGORIES:
        print(f"{C.RED}Nepoznata kategorija.{C.RESET}")
        return

    print("\nTip provere:")
    types = core.CATEGORY_CHECK_TYPES[cat]
    for i, (ct, desc) in enumerate(types, 1):
        print(f"  {i}. {desc}")
    choice = input("Izbor: ").strip()
    try:
        check_type, _ = types[int(choice) - 1]
    except (ValueError, IndexError):
        print(f"{C.RED}Nepoznat tip.{C.RESET}")
        return

    name = _prompt("Naziv targeta (npr. 'Prod web server')")
    address = _prompt("Adresa/host/putanja/ime (zavisi od tipa provere)")

    params = {}
    if check_type == "port":
        params["port"] = int(_prompt("Port", "22"))
    elif check_type == "http_status":
        params["expected_status"] = int(_prompt("Ocekivani HTTP status", "200"))
    elif check_type == "ssl_expiry":
        params["port"] = int(_prompt("Port", "443"))
        params["warn_days"] = int(_prompt("Upozori kada ostane manje od (dana)", "14"))
    elif check_type == "systemd_service":
        params["service_name"] = _prompt("Ime systemd servisa (npr. nginx)")
    elif check_type == "docker_container":
        params["container_name"] = _prompt("Ime docker container-a", address)
    elif check_type == "process_running":
        params["process_name"] = _prompt("Ime procesa (npr. python3)", address)
    elif check_type == "disk_space":
        params["threshold_percent"] = int(_prompt("Prag upozorenja (%)", "90"))

    import config
    interval = int(_prompt("Interval provere (sekunde)", str(config.DEFAULT_CHECK_INTERVAL_SEC)))

    core.add_target(name, core.CATEGORIES[cat], check_type, address, params, interval)
    print(f"{C.GREEN}Target '{name}' dodat.{C.RESET}")


def menu_list_status():
    results = core.check_all_targets()
    if not results:
        print(f"{C.YELLOW}Nema definisanih targeta. Dodaj prvi preko opcije 1.{C.RESET}")
        return

    print(f"\n{C.BOLD}--- Live status svih targeta ---{C.RESET}")
    print(f"{'ID':<4}{'Naziv':<22}{'Kategorija':<14}{'Tip':<18}{'Status':<10}{'Poruka'}")
    print("-" * 90)
    for r in results:
        color = C.GREEN if r["status"] == "ok" else C.RED
        status_label = "OK" if r["status"] == "ok" else "FAIL"
        print(f"{r['id']:<4}{r['name']:<22}{r['category']:<14}{r['check_type']:<18}"
              f"{color}{status_label:<10}{C.RESET}{r['message']}")


def menu_target_details():
    targets = core.list_targets()
    if not targets:
        print(f"{C.YELLOW}Nema targeta.{C.RESET}")
        return
    tid = _prompt("ID targeta za detalje")
    try:
        t = core.get_target(int(tid))
    except (ValueError, TypeError):
        t = None
    if not t:
        print(f"{C.RED}Target ne postoji.{C.RESET}")
        return
    print(f"\n{C.BOLD}Target #{t['id']}: {t['name']}{C.RESET}")
    print(f"  Kategorija: {t['category']}")
    print(f"  Tip provere: {t['check_type']}")
    print(f"  Adresa: {t['address']}")
    print(f"  Parametri: {t['params']}")
    print(f"  Interval: {t['interval_sec']}s")
    print(f"  Poslednji status: {t['last_status']} ({t['last_message']})")
    print(f"  Poslednja provera: {t['last_checked']}")


def menu_remove_target():
    targets = core.list_targets()
    if not targets:
        print(f"{C.YELLOW}Nema targeta za brisanje.{C.RESET}")
        return
    for t in targets:
        print(f"  {t['id']}. {t['name']} ({t['check_type']})")
    tid = _prompt("ID targeta za brisanje")
    try:
        core.delete_target(int(tid))
        print(f"{C.GREEN}Target obrisan.{C.RESET}")
    except (ValueError, TypeError):
        print(f"{C.RED}Neispravan ID.{C.RESET}")


def run():
    """Ulazna tacka modula - poziva se iz main.py"""
    while True:
        print(f"\n{C.CYAN}{C.BOLD}=== Monitoring — Sve na jednom mestu ==={C.RESET}")
        print("1. Dodaj target")
        print("2. Prikazi live status svih targeta")
        print("3. Detalji za jedan target")
        print("4. Ukloni target")
        print("0. Nazad")
        choice = input("Izbor: ").strip()

        if choice == "1":
            menu_add_target()
        elif choice == "2":
            menu_list_status()
        elif choice == "3":
            menu_target_details()
        elif choice == "4":
            menu_remove_target()
        elif choice == "0":
            break
        else:
            print(f"{C.RED}Nepoznata opcija.{C.RESET}")
