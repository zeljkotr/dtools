"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / s3
Purpose: List buckets, list/upload/download/delete objects.

Auth: uses boto3's default credential chain (IAM role when running on an
EC2 instance, or local ~/.aws/credentials / env vars when running locally).
No access keys are ever hardcoded or stored in this module.
"""

from dataclasses import dataclass
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
except ImportError:
    boto3 = None


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


def _get_client(region: str = "us-east-1"):
    if boto3 is None:
        raise AwsS3Error(
            "boto3 nije instaliran. Pokreni: pip install boto3 --break-system-packages"
        )
    return boto3.client("s3", region_name=region)


def _wrap_errors(func):
    """Small helper to keep error handling consistent across functions below."""
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NoCredentialsError:
            raise AwsS3Error(
                "Nema AWS kredencijala. Ako si na EC2 instanci, proveri IAM rolu. "
                "Ako radis lokalno, proveri ~/.aws/credentials."
            )
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
def download_file(bucket: str, key: str, local_path: str, region: str = "us-east-1") -> None:
    client = _get_client(region)
    client.download_file(bucket, key, local_path)


@_wrap_errors
def delete_object(bucket: str, key: str, region: str = "us-east-1") -> None:
    client = _get_client(region)
    client.delete_object(Bucket=bucket, Key=key)