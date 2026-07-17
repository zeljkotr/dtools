"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: home (CLI menu)
"""

from modules.home import config as home_config
from modules.home import core as home_core

DEFAULT_REGION = "us-east-1"


def _print_dashboard():
    data = home_core.build_dashboard_data(DEFAULT_REGION)

    if "ec2_status" in data:
        d = data["ec2_status"]
        print("\n  📦 EC2")
        if d.get("ok"):
            print(f"     Running: {d['running']}  Stopped: {d['stopped']}  Ukupno: {d['total']}")
        else:
            print(f"     ❌ {d.get('error')}")

    if "s3_status" in data:
        d = data["s3_status"]
        print("\n  🪣 S3")
        if d.get("ok"):
            print(f"     Zdravi: {d['healthy']}  Upozorenje: {d['warning']}  Problem: {d['failing']}  Ukupno: {d['total']}")
        else:
            print(f"     ❌ {d.get('error')}")

    if "monitoring_summary" in data:
        d = data["monitoring_summary"]
        print("\n  🖥️  Monitoring")
        print(f"     OK: {d['ok_count']}  FAIL: {d['fail_count']}  Ukupno: {d['total']}")

    if "disk_usage" in data:
        d = data["disk_usage"]
        print("\n  💾 Disk")
        if not d["disks"]:
            print("     Nema disk_space targeta.")
        for disk in d["disks"]:
            pct = f"{disk['percent']}%" if disk["percent"] is not None else "?"
            print(f"     {disk['name']}: {pct}")

    if "ec2_cpu" in data:
        d = data["ec2_cpu"]
        print("\n  🔥 EC2 CPU")
        if d.get("ok"):
            if not d["instances"]:
                print("     Nema pokrenutih instanci.")
            for inst in d["instances"]:
                cpu = f"{inst['cpu_percent']}%" if inst["cpu_percent"] is not None else "nema podataka jos"
                print(f"     {inst['name']}: {cpu}")
        else:
            print(f"     ❌ {d.get('error')}")


def run() -> None:
    while True:
        print("\n" + "=" * 50)
        print("  dtool — Moj Dashboard")
        print("=" * 50)
        _print_dashboard()

        enabled = home_config.list_enabled_widgets()
        print("\n  Ukljuceni widgeti:")
        for wid, label in home_config.WIDGET_CATALOG.items():
            mark = "✅" if wid in enabled else "  "
            print(f"  {mark} {wid} - {label}")

        print("\n  1. Dodaj widget")
        print("  2. Ukloni widget")
        print("  0. Nazad")

        choice = input("\n  Izbor: ").strip()

        if choice == "1":
            wid = input("  ID widgeta za dodavanje: ").strip()
            if wid in home_config.WIDGET_CATALOG:
                home_config.add_widget(wid)
                print("  ✅ Dodato.")
            else:
                print("  ❌ Nepoznat widget ID.")

        elif choice == "2":
            wid = input("  ID widgeta za uklanjanje: ").strip()
            home_config.remove_widget(wid)
            print("  ✅ Uklonjeno.")

        elif choice == "0":
            break

        else:
            print("  Nevazeci izbor, probaj ponovo.")