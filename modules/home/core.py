"""
dtool — devops swiss army knife · by Zeljko Tripcevski
Module: home / core
Purpose: Gathers data for each enabled widget on the "Moj Dashboard" home
screen, by calling the SAME core functions the AWS and Monitoring modules
already use (no duplicated logic, just aggregation for a single overview).
"""

import re

from modules.home import config as home_config


def _parse_disk_percent(message: str):
    """Extracts the numeric percentage from a disk_space check message
    like 'Usage 45.2% (threshold 90%)'. Returns None if it can't parse."""
    match = re.search(r"Usage ([\d.]+)%", message)
    if match:
        return float(match.group(1))
    return None


def get_ec2_status_data(region: str = "us-east-1"):
    from modules.aws.ec2 import core as ec2_core
    try:
        instances = ec2_core.list_instances(region)
        return {
            "ok": True,
            "running": sum(1 for i in instances if i.state == "running"),
            "stopped": sum(1 for i in instances if i.state in ("stopped", "terminated")),
            "other": sum(1 for i in instances if i.state not in ("running", "stopped", "terminated")),
            "total": len(instances),
        }
    except ec2_core.AwsEc2Error as e:
        return {"ok": False, "error": str(e)}


def get_s3_status_data(region: str = "us-east-1"):
    from modules.aws.s3 import core as s3_core
    try:
        buckets = s3_core.list_buckets(region)
        healthy = 0
        warning = 0
        failing = 0
        for b in buckets:
            status, _ = s3_core.bucket_health(b.name, region)
            if status == "ok":
                healthy += 1
            elif status == "warn":
                warning += 1
            else:
                failing += 1
        return {"ok": True, "total": len(buckets), "healthy": healthy, "warning": warning, "failing": failing}
    except s3_core.AwsS3Error as e:
        return {"ok": False, "error": str(e)}


def get_monitoring_summary_data():
    from modules.monitoring import core as monitoring_core
    targets = monitoring_core.list_targets()
    ok_count = sum(1 for t in targets if t["last_status"] == "ok")
    fail_count = sum(1 for t in targets if t["last_status"] == "fail")
    unknown_count = len(targets) - ok_count - fail_count
    return {"ok": True, "total": len(targets), "ok_count": ok_count, "fail_count": fail_count, "unknown_count": unknown_count}


def get_disk_usage_data():
    from modules.monitoring import core as monitoring_core
    targets = monitoring_core.list_targets()
    disks = []
    for t in targets:
        if t["check_type"] != "disk_space":
            continue
        percent = _parse_disk_percent(t["last_message"] or "")
        disks.append({"name": t["name"], "percent": percent, "status": t["last_status"]})
    return {"ok": True, "disks": disks}


def get_ec2_cpu_data(region: str = "us-east-1"):
    from modules.aws.ec2 import core as ec2_core
    try:
        instances = ec2_core.list_instances(region)
        cpu_data = []
        for inst in instances:
            if inst.state != "running":
                continue
            cpu = ec2_core.get_cpu_utilization(inst.instance_id, region)
            cpu_data.append({"name": inst.name, "cpu_percent": cpu})
        return {"ok": True, "instances": cpu_data}
    except ec2_core.AwsEc2Error as e:
        return {"ok": False, "error": str(e)}


_WIDGET_LOADERS = {
    "ec2_status": get_ec2_status_data,
    "s3_status": get_s3_status_data,
    "monitoring_summary": get_monitoring_summary_data,
    "disk_usage": get_disk_usage_data,
    "ec2_cpu": get_ec2_cpu_data,
}


def build_dashboard_data(region: str = "us-east-1") -> dict:
    """
    Returns {widget_id: data} for every currently enabled widget.
    A failure loading one widget's data does not break the others.
    """
    enabled = home_config.list_enabled_widgets()
    result = {}
    for widget_id in enabled:
        loader = _WIDGET_LOADERS.get(widget_id)
        if not loader:
            continue
        try:
            if widget_id in ("ec2_status", "s3_status", "ec2_cpu"):
                result[widget_id] = loader(region)
            else:
                result[widget_id] = loader()
        except Exception as e:
            result[widget_id] = {"ok": False, "error": str(e)}
    return result