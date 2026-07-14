"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / settings (CLI menu) — Add/Edit/Delete AWS credentials.
"""

from modules.aws import config as aws_config


def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "..." + value[-4:]


def run() -> None:
    while True:
        print("\n" + "=" * 50)
        print("  dtool — AWS Credentials")
        print("=" * 50)

        creds = aws_config.load_credentials()
        if creds:
            print(f"  Trenutno sacuvano: Access Key {_mask(creds['access_key'])}, "
                  f"Region {creds.get('region', 'us-east-1')}")
        else:
            print("  Nema sacuvanih kredencijala — koristi se IAM rola / default lanac.")

        print("\n  1. Dodaj kredencijale (Add)")
        print("  2. Izmeni kredencijale (Edit)")
        print("  3. Obrisi kredencijale (Delete) — vrati se na IAM rolu")
        print("  0. Nazad")

        choice = input("\n  Izbor: ").strip()

        if choice in ("1", "2"):
            access_key = input("  AWS Access Key ID: ").strip()
            secret_key = input("  AWS Secret Access Key: ").strip()
            region = input("  Region [us-east-1]: ").strip() or "us-east-1"
            session_token = input("  Session Token (Enter ako nemas): ").strip()

            if not access_key or not secret_key:
                print("  ❌ Access Key i Secret Key su obavezni.")
                continue

            aws_config.save_credentials(access_key, secret_key, region, session_token)
            print("  ✅ Kredencijali sacuvani.")

        elif choice == "3":
            if not creds:
                print("  Nema sta da se obrise.")
            else:
                confirm = input("  Sigurno brises sacuvane kredencijale? (da/ne): ").strip().lower()
                if confirm == "da":
                    aws_config.clear_credentials()
                    print("  ✅ Obrisano. Sada se koristi IAM rola / default lanac.")
                else:
                    print("  Otkazano.")

        elif choice == "0":
            break

        else:
            print("  Nevazeci izbor, probaj ponovo.")