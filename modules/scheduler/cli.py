"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: scheduler (CLI menu)
"""

from modules.scheduler import core as scheduler_core


def run() -> None:
    while True:
        status = scheduler_core.get_status()
        print("\n" + "=" * 50)
        print("  dtool — Scheduler (background checks)")
        print("=" * 50)
        print(f"  Status: {status}")
        print("\n  1. Install (Add) - runs checks on a schedule")
        print("  2. Change interval (Edit)")
        print("  3. Uninstall (Delete)")
        print("  4. Show next run time")
        print("  0. Back")

        choice = input("\n  Choice: ").strip()

        try:
            if choice == "1":
                interval = input("  Interval in seconds [60]: ").strip()
                interval = int(interval) if interval else 60
                scheduler_core.install(interval)
                print("  ✅ Installed and started.")
                print("  Note: for this to keep running after you log out of SSH,")
                print("  run once (needs sudo): sudo loginctl enable-linger $(whoami)")

            elif choice == "2":
                interval = input("  New interval in seconds: ").strip()
                if interval:
                    scheduler_core.update_interval(int(interval))
                    print("  ✅ Interval updated.")

            elif choice == "3":
                confirm = input("  Uninstall the background scheduler? (yes/no): ").strip().lower()
                if confirm == "yes":
                    scheduler_core.uninstall()
                    print("  ✅ Uninstalled.")

            elif choice == "4":
                print(scheduler_core.get_next_run())

            elif choice == "0":
                break

            else:
                print("  Invalid choice, try again.")

        except scheduler_core.SchedulerError as e:
            print(f"  ❌ Error: {e}")