"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws (top-level menu)
"""

from modules.aws.ec2 import cli as ec2_cli
from modules.aws.s3 import cli as s3_cli

SERVICES = {
    "1": ("EC2 (instance management)", ec2_cli.run),
    "2": ("S3 (bucket/object storage)", s3_cli.run),
}


def run() -> None:
    while True:
        print("\n" + "=" * 50)
        print("  dtool — AWS")
        print("=" * 50)
        for key, (label, _) in SERVICES.items():
            print(f"  {key}. {label}")
        print("  0. Nazad na glavni meni")

        choice = input("\n  Izbor: ").strip()

        if choice == "0":
            break
        elif choice in SERVICES:
            _, handler = SERVICES[choice]
            handler()
        else:
            print("  Nevazeci izbor, probaj ponovo.")
