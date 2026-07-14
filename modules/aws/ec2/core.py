"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: aws / ec2
Purpose: List, start, stop, and check status of EC2 instances.

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


class AwsEc2Error(Exception):
    """Raised for any aws/ec2 module failure, with a human-readable message."""
    pass


@dataclass
class InstanceInfo:
    instance_id: str
    name: str
    state: str
    instance_type: str
    public_ip: Optional[str]
    private_ip: Optional[str]
    az: str


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
        raise AwsEc2Error(
            "boto3 nije instaliran. Pokreni: pip install boto3 --break-system-packages"
        )
    return _get_session(region).client("ec2")


def _name_from_tags(tags) -> str:
    if not tags:
        return "(bez imena)"
    for tag in tags:
        if tag.get("Key") == "Name":
            return tag.get("Value", "(bez imena)")
    return "(bez imena)"


def list_instances(region: str = "us-east-1") -> list[InstanceInfo]:
    """Return all EC2 instances in the given region (any state)."""
    client = _get_client(region)
    try:
        response = client.describe_instances()
    except NoCredentialsError:
        raise AwsEc2Error(
            "Nema AWS kredencijala. Podesi ih u AWS > Credentials, ili proveri "
            "da li je IAM rola zakacena (ako si na EC2 instanci)."
        )
    except EndpointConnectionError:
        raise AwsEc2Error("Ne mogu da se povezem na AWS (proveri internet konekciju).")
    except ClientError as e:
        raise AwsEc2Error(f"AWS je odbio zahtev: {e.response['Error']['Message']}")

    instances = []
    for reservation in response.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            instances.append(
                InstanceInfo(
                    instance_id=inst["InstanceId"],
                    name=_name_from_tags(inst.get("Tags")),
                    state=inst["State"]["Name"],
                    instance_type=inst["InstanceType"],
                    public_ip=inst.get("PublicIpAddress"),
                    private_ip=inst.get("PrivateIpAddress"),
                    az=inst.get("Placement", {}).get("AvailabilityZone", "?"),
                )
            )
    return instances


def get_instance_status(instance_id: str, region: str = "us-east-1") -> str:
    client = _get_client(region)
    try:
        response = client.describe_instances(InstanceIds=[instance_id])
    except NoCredentialsError:
        raise AwsEc2Error("Nema AWS kredencijala. Podesi ih u AWS > Credentials.")
    except ClientError as e:
        raise AwsEc2Error(f"AWS je odbio zahtev: {e.response['Error']['Message']}")

    reservations = response.get("Reservations", [])
    if not reservations or not reservations[0].get("Instances"):
        raise AwsEc2Error(f"Instanca {instance_id} nije pronadjena.")
    return reservations[0]["Instances"][0]["State"]["Name"]


def start_instance(instance_id: str, region: str = "us-east-1") -> str:
    client = _get_client(region)
    try:
        response = client.start_instances(InstanceIds=[instance_id])
    except NoCredentialsError:
        raise AwsEc2Error("Nema AWS kredencijala. Podesi ih u AWS > Credentials.")
    except ClientError as e:
        raise AwsEc2Error(f"Ne mogu da pokrenem instancu: {e.response['Error']['Message']}")
    return response["StartingInstances"][0]["CurrentState"]["Name"]


def stop_instance(instance_id: str, region: str = "us-east-1") -> str:
    client = _get_client(region)
    try:
        response = client.stop_instances(InstanceIds=[instance_id])
    except NoCredentialsError:
        raise AwsEc2Error("Nema AWS kredencijala. Podesi ih u AWS > Credentials.")
    except ClientError as e:
        raise AwsEc2Error(f"Ne mogu da zaustavim instancu: {e.response['Error']['Message']}")
    return response["StoppingInstances"][0]["CurrentState"]["Name"]


def reboot_instance(instance_id: str, region: str = "us-east-1") -> None:
    client = _get_client(region)
    try:
        client.reboot_instances(InstanceIds=[instance_id])
    except NoCredentialsError:
        raise AwsEc2Error("Nema AWS kredencijala. Podesi ih u AWS > Credentials.")
    except ClientError as e:
        raise AwsEc2Error(f"Ne mogu da restartujem instancu: {e.response['Error']['Message']}")