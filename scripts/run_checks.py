#!/usr/bin/env python3
"""
dtool — devops swiss army knife · by Zeljko Tripcevski
scripts/run_checks.py

Standalone entry point used by the dtool-checks systemd timer/service.
Runs one full monitoring check cycle (all targets) and exits.

This is what makes alerting actually work continuously - without this
running on a schedule, checks (and therefore alerts) only fire when
someone happens to open the web dashboard in a browser.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.monitoring import core

if __name__ == "__main__":
    results = core.check_all_targets()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    fail_count = len(results) - ok_count
    print(f"dtool check cycle: {ok_count} ok, {fail_count} fail, {len(results)} total")