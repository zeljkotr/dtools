"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / s3 (CLI menu)
"""

from modules.aws.s3 import core

DEFAULT_REGION = "us-east-1"


def _pick_bucket() -> str | None:
    try:
        buckets = core.list_buckets(DEFAULT_REGION)
    except core.AwsS3Error as e:
        print(f"  ❌ Greska: {e}")
        return None

    if not buckets:
        print("  Nema bucket-a na ovom nalogu.")
        return None

    print("\n  Dostupni bucket-i:")
    for i, b in enumerate(buckets, start=1):
        print(f"  {i}. {b.name}  (napravljen: {b.creation_date})")

    choice = input("\n  Izaberi broj bucket-a (ili Enter za nazad): ").strip()
    if not choice:
        return None
    try:
        return buckets[int(choice) - 1].name
    except (ValueError, IndexError):
        print("  Nevazeci izbor.")
        return None


def run() -> None:
    while True:
        print("\n" + "=" * 50)
        print("  dtool — aws / s3")
        print("=" * 50)
        print("  1. Prikazi sve bucket-e")
        print("  2. Napravi bucket (Create)")
        print("  3. Obrisi bucket (Delete) — mora biti prazan")
        print("  4. Prikazi fajlove u bucket-u")
        print("  5. Upload fajla")
        print("  6. Download fajla")
        print("  7. Obrisi fajl iz bucket-a")
        print("  0. Nazad")

        choice = input("\n  Izbor: ").strip()

        try:
            if choice == "1":
                buckets = core.list_buckets(DEFAULT_REGION)
                if not buckets:
                    print("  Nema bucket-a.")
                for b in buckets:
                    print(f"  🪣 {b.name}  (napravljen: {b.creation_date})")

            elif choice == "2":
                name = input("  Ime novog bucket-a (mora biti globalno jedinstveno): ").strip()
                if name:
                    core.create_bucket(name, DEFAULT_REGION)
                    print(f"  ✅ Bucket '{name}' napravljen.")

            elif choice == "3":
                bucket = _pick_bucket()
                if bucket:
                    confirm = input(
                        f"  ⚠️  TRAJNO brises bucket '{bucket}' (mora biti prazan)? (da/ne): "
                    ).strip().lower()
                    if confirm == "da":
                        core.delete_bucket(bucket, DEFAULT_REGION)
                        print("  ✅ Bucket obrisan.")
                    else:
                        print("  Otkazano.")

            elif choice == "4":
                bucket = _pick_bucket()
                if bucket:
                    objects = core.list_objects(bucket, region=DEFAULT_REGION)
                    if not objects:
                        print("  Bucket je prazan.")
                    for obj in objects:
                        size_kb = obj.size_bytes / 1024
                        print(f"  📄 {obj.key:<40} {size_kb:>8.1f} KB   {obj.last_modified}")

            elif choice == "5":
                bucket = _pick_bucket()
                if bucket:
                    local_path = input("  Putanja lokalnog fajla: ").strip()
                    key = core.upload_file(local_path, bucket, region=DEFAULT_REGION)
                    print(f"  ✅ Upload-ovano kao: {key}")

            elif choice == "6":
                bucket = _pick_bucket()
                if bucket:
                    key = input("  Ime fajla (key) u bucket-u: ").strip()
                    local_path = input("  Gde da sacuvam lokalno (putanja): ").strip()
                    core.download_file(bucket, key, local_path, region=DEFAULT_REGION)
                    print(f"  ✅ Sacuvano u: {local_path}")

            elif choice == "7":
                bucket = _pick_bucket()
                if bucket:
                    key = input("  Ime fajla (key) za brisanje: ").strip()
                    confirm = input(f"  Sigurno brises '{key}'? (da/ne): ").strip().lower()
                    if confirm == "da":
                        core.delete_object(bucket, key, region=DEFAULT_REGION)
                        print("  ✅ Obrisano.")
                    else:
                        print("  Otkazano.")

            elif choice == "0":
                break

            else:
                print("  Nevazeci izbor, probaj ponovo.")

        except core.AwsS3Error as e:
            print(f"  ❌ Greska: {e}")