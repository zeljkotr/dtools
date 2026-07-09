"""
main.py - DevOps Multitool

Glavni meni / router. Svaki modul se dodaje kao posebna opcija.
Moduli koji jos ne postoje prikazuju "Coming soon" - dodajemo ih
postepeno kako napredujes kroz AWS/K8s/Terraform plan.
"""

from modules import monitoring

# Kada napravimo nove module, samo ih importujemo ovde, npr:
# from modules import aws_ec2, docker_tools, backup, security_scan, git_tools


class C:
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def _placeholder(name):
    print(f"\n{C.YELLOW}[{name}] modul jos nije implementiran — dolazi uskoro.{C.RESET}")


def main_menu():
    while True:
        print(f"\n{C.CYAN}{C.BOLD}========================================")
        print("        DEVOPS MULTITOOL")
        print(f"========================================{C.RESET}")
        print("1. AWS EC2 Management        [coming soon]")
        print("2. Docker Tools              [coming soon]")
        print("3. Monitoring (servers, services, containers...)")
        print("4. Backup Manager            [coming soon]")
        print("5. Security Scanner          [coming soon]")
        print("6. Git / CI-CD Tools         [coming soon]")
        print("7. Pokreni web dashboard (Flask, http://localhost:5000)")
        print("0. Exit")

        choice = input("\nIzbor: ").strip()

        if choice == "1":
            _placeholder("AWS EC2 Management")
        elif choice == "2":
            _placeholder("Docker Tools")
        elif choice == "3":
            monitoring.run()
        elif choice == "4":
            _placeholder("Backup Manager")
        elif choice == "5":
            _placeholder("Security Scanner")
        elif choice == "6":
            _placeholder("Git / CI-CD Tools")
        elif choice == "7":
            print(f"\n{C.YELLOW}Pokretanje web dashboard-a... Ctrl+C da zaustavis i vratis se u ovaj meni.{C.RESET}")
            import subprocess, sys, os
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "webapp", "app.py")])
        elif choice == "0":
            print("Cao!")
            break
        else:
            print("Nepoznata opcija.")


if __name__ == "__main__":
    main_menu()
