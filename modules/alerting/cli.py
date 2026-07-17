"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: alerting (CLI menu) - Add/Edit/Delete alert channels, test send.
"""

from modules.alerting import config as alert_config
from modules.alerting import core as alerting_core


def _print_channels(channels):
    if not channels:
        print("  No alert channels configured yet.")
        return
    print(f"\n  {'#':<3} {'Name':<20} {'Type':<10} {'Status':<10}")
    print("  " + "-" * 50)
    for i, c in enumerate(channels, start=1):
        status = "enabled" if c.get("enabled", True) else "disabled"
        print(f"  {i:<3} {c['name']:<20} {c['type']:<10} {status:<10}")


def _pick_channel(channels):
    _print_channels(channels)
    if not channels:
        return None
    choice = input("\n  Pick channel number (or Enter to go back): ").strip()
    if not choice:
        return None
    try:
        return channels[int(choice) - 1]
    except (ValueError, IndexError):
        print("  Invalid choice.")
        return None


def run() -> None:
    while True:
        channels = alert_config.list_channels()
        print("\n" + "=" * 50)
        print("  dtool — Alerting")
        print("=" * 50)
        _print_channels(channels)
        print("\n  1. Add channel")
        print("  2. Edit channel")
        print("  3. Delete channel")
        print("  4. Enable/disable channel")
        print("  5. Send test message")
        print("  0. Back")

        choice = input("\n  Choice: ").strip()

        if choice == "1":
            channel_type = input("  Channel type (email/telegram): ").strip().lower()
            name = input("  Channel name (e.g. 'My email'): ").strip()

            if channel_type == "email":
                cfg = {
                    "smtp_server": input("  SMTP server (e.g. smtp.gmail.com): ").strip(),
                    "smtp_port": input("  SMTP port [587]: ").strip() or "587",
                    "smtp_user": input("  SMTP username (email): ").strip(),
                    "smtp_password": input("  SMTP password (app password): ").strip(),
                    "from_addr": input("  From address (Enter = same as username): ").strip(),
                    "to_addr": input("  Send to email: ").strip(),
                }
                if not cfg["from_addr"]:
                    cfg["from_addr"] = cfg["smtp_user"]
            elif channel_type == "telegram":
                cfg = {
                    "bot_token": input("  Telegram Bot Token: ").strip(),
                    "chat_id": input("  Telegram Chat ID: ").strip(),
                }
            else:
                print("  ❌ Unknown type. Use 'email' or 'telegram'.")
                continue

            alert_config.add_channel(channel_type, name, cfg)
            print("  ✅ Channel added.")

        elif choice == "2":
            target = _pick_channel(channels)
            if target:
                name = input(f"  New name [{target['name']}]: ").strip() or target["name"]
                print("  (Enter a new value, or press Enter to keep the current one)")
                new_config = dict(target["config"])
                for key in new_config:
                    val = input(f"  {key} [{new_config[key]}]: ").strip()
                    if val:
                        new_config[key] = val
                alert_config.update_channel(target["id"], name, new_config, target.get("enabled", True))
                print("  ✅ Channel updated.")

        elif choice == "3":
            target = _pick_channel(channels)
            if target:
                confirm = input(f"  Delete channel '{target['name']}'? (yes/no): ").strip().lower()
                if confirm == "yes":
                    alert_config.delete_channel(target["id"])
                    print("  ✅ Deleted.")

        elif choice == "4":
            target = _pick_channel(channels)
            if target:
                new_state = not target.get("enabled", True)
                alert_config.toggle_channel(target["id"], new_state)
                print(f"  ✅ Channel is now {'enabled' if new_state else 'disabled'}.")

        elif choice == "5":
            target = _pick_channel(channels)
            if target:
                success, error = alerting_core.send_to_channel(
                    target, "dtool test", "This is a test message from the dtool alerting module."
                )
                if success:
                    print("  ✅ Test message sent.")
                else:
                    print(f"  ❌ Error: {error}")

        elif choice == "0":
            break

        else:
            print("  Invalid choice, try again.")