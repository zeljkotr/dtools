"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / ec2 (CLI menu)
"""

from modules.aws.ec2 import core

DEFAULT_REGION = "us-east-1"


def _print_instance_table(instances: list[core.InstanceInfo]) -> None:
    if not instances:
        print("  Nema pronadjenih instanci u ovom regionu.")
        return

    print(f"\n  {'#':<3} {'Ime':<22} {'Instance ID':<20} {'Stanje':<10} {'Tip':<12} {'Public IP':<16}")
    print("  " + "-" * 85)
    for i, inst in enumerate(instances, start=1):
        state_marker = "🟢" if inst.state == "running" else "🔴" if inst.state == "stopped" else "🟡"
        print(
            f"  {i:<3} {inst.name:<22} {inst.instance_id:<20} "
            f"{state_marker} {inst.state:<8} {inst.instance_type:<12} {inst.public_ip or '-':<16}"
        )


def _choose_instance(instances: list[core.InstanceInfo]) -> core.InstanceInfo | None:
    _print_instance_table(instances)
    if not instances:
        return None
    choice = input("\n  Izaberi broj instance (ili Enter za nazad): ").strip()
    if not choice:
        return None
    try:
        idx = int(choice) - 1
        return instances[idx]
    except (ValueError, IndexError):
        print("  Nevazeci izbor.")
        return None


def run() -> None:
    while True:
        print("\n" + "=" * 50)
        print("  dtool — aws_ec2")
        print("=" * 50)
        print("  1. Prikazi sve instance")
        print("  2. Dodaj instancu (Launch)")
        print("  3. Izmeni ime instance (Rename)")
        print("  4. Obrisi instancu (Terminate)")
        print("  5. Pokreni instancu (start)")
        print("  6. Zaustavi instancu (stop)")
        print("  7. Restartuj instancu (reboot)")
        print("  8. Proveri status jedne instance")
        print("  0. Nazad na glavni meni")

        choice = input("\n  Izbor: ").strip()

        try:
            if choice == "1":
                instances = core.list_instances(DEFAULT_REGION)
                _print_instance_table(instances)

            elif choice == "2":
                name = input("  Ime nove instance: ").strip()
                ami_id = input("  AMI ID (npr. ami-0abcdef1234567890): ").strip()
                instance_type = input("  Instance type [t3.micro]: ").strip() or "t3.micro"
                key_name = input("  Key pair ime (npr. aws-win-key): ").strip()
                if not (name and ami_id and key_name):
                    print("  ❌ Ime, AMI ID i Key pair su obavezni.")
                else:
                    new_id = core.launch_instance(name, ami_id, instance_type, key_name, DEFAULT_REGION)
                    print(f"  ✅ Instanca pokrenuta: {new_id}")

            elif choice == "3":
                instances = core.list_instances(DEFAULT_REGION)
                target = _choose_instance(instances)
                if target:
                    new_name = input(f"  Novo ime za '{target.name}': ").strip()
                    if new_name:
                        core.rename_instance(target.instance_id, new_name, DEFAULT_REGION)
                        print("  ✅ Ime izmenjeno.")

            elif choice == "4":
                instances = core.list_instances(DEFAULT_REGION)
                target = _choose_instance(instances)
                if target:
                    confirm = input(
                        f"  ⚠️  TRAJNO brises '{target.name}' ({target.instance_id})? (da/ne): "
                    ).strip().lower()
                    if confirm == "da":
                        core.terminate_instance(target.instance_id, DEFAULT_REGION)
                        print("  ✅ Instanca se terminise.")
                    else:
                        print("  Otkazano.")

            elif choice == "5":
                instances = core.list_instances(DEFAULT_REGION)
                target = _choose_instance(instances)
                if target:
                    if target.state == "running":
                        print(f"  Instanca {target.name} je vec pokrenuta.")
                    else:
                        new_state = core.start_instance(target.instance_id, DEFAULT_REGION)
                        print(f"  ✅ Pokrenuto. Novo stanje: {new_state}")

            elif choice == "6":
                instances = core.list_instances(DEFAULT_REGION)
                target = _choose_instance(instances)
                if target:
                    if target.state == "stopped":
                        print(f"  Instanca {target.name} je vec zaustavljena.")
                    else:
                        confirm = input(
                            f"  Sigurno zaustavljas '{target.name}'? (da/ne): "
                        ).strip().lower()
                        if confirm == "da":
                            new_state = core.stop_instance(target.instance_id, DEFAULT_REGION)
                            print(f"  ✅ Zaustavljeno. Novo stanje: {new_state}")
                        else:
                            print("  Otkazano.")

            elif choice == "7":
                instances = core.list_instances(DEFAULT_REGION)
                target = _choose_instance(instances)
                if target:
                    confirm = input(
                        f"  Sigurno restartujes '{target.name}'? (da/ne): "
                    ).strip().lower()
                    if confirm == "da":
                        core.reboot_instance(target.instance_id, DEFAULT_REGION)
                        print("  ✅ Restart pokrenut (mozda potraje par sekundi).")
                    else:
                        print("  Otkazano.")

            elif choice == "8":
                instance_id = input("  Unesi Instance ID: ").strip()
                status = core.get_instance_status(instance_id, DEFAULT_REGION)
                print(f"  Stanje instance {instance_id}: {status}")

            elif choice == "0":
                break

            else:
                print("  Nevazeci izbor, probaj ponovo.")

        except core.AwsEc2Error as e:
            print(f"  ❌ Greska: {e}")