"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / s3
Purpose: Create/delete buckets, list/upload/download/delete objects,
         check bucket health (for dashboard status semafor).

Auth priority:
  1. Credentials saved via modules/aws/config.py (GUI/CLI "AWS Credentials"
     settings screen), if present.
  2. Otherwise, boto3's default credential chain (IAM role when running on
     an EC2 instance, or local ~/.aws/credentials / env vars).
No access keys are ever hardcoded in this file.
"""

from dataclasses import dataclass
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
except ImportError:
    boto3 = None

from modules.aws import config as aws_config


class AwsS3Error(Exception):
    """Raised for any aws/s3 module failure, with a human-readable message."""
    pass


@dataclass
class BucketInfo:
    name: str
    creation_date: str


@dataclass
class ObjectInfo:
    key: str
    size_bytes: int
    last_modified: str


def _get_session(region: str = "us-east-1"):
    creds = aws_config.load_credentials()
    if creds:
        return boto3.Session(
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            aws_session_token=(creds.get("session_token") or None),
            region_name=creds.get("region", region),
        )
    return boto3.Session(region_name=region)


def _get_client(region: str = "us-east-1"):
    if boto3 is None:
        raise AwsS3Error(
            "boto3 nije instaliran. Pokreni: pip install boto3 --break-system-packages"
        )
    return _get_session(region).client("s3")


def _wrap_errors(func):
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NoCredentialsError:
            raise AwsS3Error("Nema AWS kredencijala. Podesi ih u AWS > Credentials.")
        except EndpointConnectionError:
            raise AwsS3Error("Ne mogu da se povezem na AWS (proveri internet konekciju).")
        except ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            raise AwsS3Error(f"AWS je odbio zahtev ({code}): {msg}")
    return inner


@_wrap_errors
def list_buckets(region: str = "us-east-1") -> list[BucketInfo]:
    client = _get_client(region)
    response = client.list_buckets()
    return [
        BucketInfo(name=b["Name"], creation_date=str(b["CreationDate"]))
        for b in response.get("Buckets", [])
    ]


@_wrap_errors
def create_bucket(bucket_name: str, region: str = "us-east-1") -> None:
    """Add — creates a new S3 bucket. Bucket names must be globally unique."""
    client = _get_client(region)
    if region == "us-east-1":
        client.create_bucket(Bucket=bucket_name)
    else:
        client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )


@_wrap_errors
def delete_bucket(bucket_name: str, region: str = "us-east-1") -> None:
    """Delete — removes a bucket. Bucket must be empty first (AWS requirement)."""
    client = _get_client(region)
    client.delete_bucket(Bucket=bucket_name)


@_wrap_errors
def list_objects(bucket: str, prefix: str = "", region: str = "us-east-1") -> list[ObjectInfo]:
    client = _get_client(region)
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [
        ObjectInfo(
            key=obj["Key"],
            size_bytes=obj["Size"],
            last_modified=str(obj["LastModified"]),
        )
        for obj in response.get("Contents", [])
    ]


@_wrap_errors
def upload_file(local_path: str, bucket: str, key: Optional[str] = None, region: str = "us-east-1") -> str:
    client = _get_client(region)
    key = key or local_path.split("/")[-1]
    client.upload_file(local_path, bucket, key)
    return key


@_wrap_errors
def upload_fileobj(fileobj, bucket: str, key: str, region: str = "us-east-1") -> str:
    """Add (web) — uploads directly from an in-memory file object (Flask upload)."""
    client = _get_client(region)
    client.upload_fileobj(fileobj, bucket, key)
    return key


@_wrap_errors
def download_file(bucket: str, key: str, local_path: str, region: str = "us-east-1") -> None:
    client = _get_client(region)
    client.download_file(bucket, key, local_path)


@_wrap_errors
def delete_object(bucket: str, key: str, region: str = "us-east-1") -> None:
    client = _get_client(region)
    client.delete_object(Bucket=bucket, Key=key)


def bucket_health(bucket_name: str, region: str = "us-east-1") -> tuple[str, str]:
    """
    Status semafor za dashboard prikaz. Vraca (status, message):
      "ok"   — bucket dostupan i ima bar 1 objekat
      "warn" — bucket dostupan, ali prazan (nije greska, samo upozorenje)
      "fail" — bucket nedostupan (obrisan, nema pristupa, mreza pukla, itd.)
    Ne baca izuzetak — dizajnirano da se sigurno zove za svaki bucket u petlji
    bez da jedan neuspesan poziv obori ceo dashboard prikaz.
    """
    try:
        client = _get_client(region)
    except AwsS3Error as e:
        return "fail", str(e)

    try:
        client.head_bucket(Bucket=bucket_name)
    except NoCredentialsError:
        return "fail", "Nema AWS kredencijala."
    except EndpointConnectionError:
        return "fail", "Ne mogu da se povezem na AWS."
    except ClientError as e:
        code = e.response["Error"]["Code"]
        return "fail", f"Bucket nedostupan ({code})"

    try:
        response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        has_objects = response.get("KeyCount", 0) > 0
    except ClientError as e:
        code = e.response["Error"]["Code"]
        return "fail", f"Ne mogu da procitam sadrzaj ({code})"

    if has_objects:
        return "ok", "Dostupan, ima sadrzaja"
    return "warn", "Dostupan, ali prazan"