"""
webapp/app.py

Flask web frontend za dtool monitoring modul.
Koristi ISTU core.py logiku kao CLI (modules/monitoring/cli.py) -
nema duplirane logike, samo drugaciji prikaz.

Pokretanje:
    cd dtool
    python3 webapp/app.py
Otvori u browseru: http://localhost:5000  (ili http://IP_SERVERA:5000)

# dtool — devops swiss army knife · by Zeljko Tripcevski
"""

import sys
import os

# Da bismo mogli da importujemo "config" i "modules" iz root foldera projekta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from modules.monitoring import core
import config

app = Flask(__name__)
app.secret_key = "dtool-dev-secret-change-me"  # samo za flash poruke, nije za produkciju


@app.route("/")
def dashboard():
    results = core.check_all_targets()
    return render_template("dashboard.html", results=results)


@app.route("/add", methods=["GET", "POST"])
def add_target():
    if request.method == "POST":
        category_key = request.form.get("category")
        check_type = request.form.get("check_type")
        name = request.form.get("name")
        address = request.form.get("address") or name
        interval = int(request.form.get("interval") or 60)

        # Parametri specificni za tip provere - skupimo sve sto pocinje sa "param_"
        params = {}
        for key, value in request.form.items():
            if key.startswith("param_") and value:
                param_name = key[len("param_"):]
                # pokusaj da konvertujes u int ako je moguce (port, threshold, itd.)
                try:
                    params[param_name] = int(value)
                except ValueError:
                    params[param_name] = value

        category_name = core.CATEGORIES.get(category_key, "Nepoznato")
        core.add_target(name, category_name, check_type, address, params, interval)
        flash(f"Target '{name}' uspesno dodat.", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "add_target.html",
        categories=core.CATEGORIES,
        category_check_types=core.CATEGORY_CHECK_TYPES,
    )


@app.route("/delete/<int:target_id>", methods=["POST"])
def delete_target(target_id):
    core.delete_target(target_id)
    flash("Target obrisan.", "info")
    return redirect(url_for("dashboard"))


@app.route("/edit/<int:target_id>", methods=["GET", "POST"])
def edit_target(target_id):
    import json

    t = core.get_target(target_id)
    if not t:
        flash("Target ne postoji.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name")
        address = request.form.get("address") or name
        interval = int(request.form.get("interval") or 60)

        params = {}
        for key, value in request.form.items():
            if key.startswith("param_") and value:
                param_name = key[len("param_"):]
                try:
                    params[param_name] = int(value)
                except ValueError:
                    params[param_name] = value

        core.update_target(target_id, name, address, params, interval)
        flash(f"Target '{name}' izmenjen.", "success")
        return redirect(url_for("dashboard"))

    existing_params = json.loads(t["params"] or "{}")
    return render_template("edit_target.html", t=t, params=existing_params)


@app.route("/target/<int:target_id>")
def target_details(target_id):
    t = core.get_target(target_id)
    if not t:
        flash("Target ne postoji.", "error")
        return redirect(url_for("dashboard"))
    return render_template("target_details.html", t=t)


@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    """
    JEDINI ulaz za agente (modules/monitoring/agent.py). Agent salje POST
    sa {token, target, status, message} - OUTBOUND sa njegove strane, a ovde
    je to obican HTTP zahtev na vec postojeci web port dtool servera
    (nema potrebe za posebnim/dodatnim portom).
    """
    data = request.get_json(silent=True) or {}

    if data.get("token") != config.AGENT_TOKEN:
        return jsonify({"error": "invalid token"}), 401

    target_name = data.get("target")
    status = data.get("status")
    message = data.get("message", "")

    if not target_name or status not in ("ok", "fail"):
        return jsonify({"error": "missing or invalid fields (target, status)"}), 400

    found = core.record_push(target_name, status, message)
    if not found:
        return jsonify({"error": f"target '{target_name}' not found "
                                  f"(add it first as an 'agent_heartbeat' target)"}), 404

    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------
# AWS rute (EC2 + S3 + Credentials) — koriste ISTI core.py kao CLI
# dtool — devops swiss army knife · by Zeljko Tripcevski
# ---------------------------------------------------------------
from modules.aws.ec2 import core as ec2_core
from modules.aws.s3 import core as s3_core
from modules.aws import config as aws_config

AWS_REGION = "us-east-1"


@app.route("/aws")
def aws_dashboard():
    return render_template("aws_dashboard.html", region=AWS_REGION)


@app.route("/aws/ec2")
def aws_ec2():
    try:
        instances = ec2_core.list_instances(AWS_REGION)
        return render_template("aws_ec2.html", instances=instances, error=None)
    except ec2_core.AwsEc2Error as e:
        return render_template("aws_ec2.html", instances=[], error=str(e))


@app.route("/aws/ec2/<instance_id>/start", methods=["POST"])
def aws_ec2_start(instance_id):
    try:
        ec2_core.start_instance(instance_id, AWS_REGION)
        flash(f"Instanca {instance_id} pokrenuta.", "success")
    except ec2_core.AwsEc2Error as e:
        flash(str(e), "error")
    return redirect(url_for("aws_ec2"))


@app.route("/aws/ec2/<instance_id>/stop", methods=["POST"])
def aws_ec2_stop(instance_id):
    try:
        ec2_core.stop_instance(instance_id, AWS_REGION)
        flash(f"Instanca {instance_id} zaustavljena.", "info")
    except ec2_core.AwsEc2Error as e:
        flash(str(e), "error")
    return redirect(url_for("aws_ec2"))


@app.route("/aws/ec2/<instance_id>/reboot", methods=["POST"])
def aws_ec2_reboot(instance_id):
    try:
        ec2_core.reboot_instance(instance_id, AWS_REGION)
        flash(f"Instanca {instance_id} se restartuje.", "info")
    except ec2_core.AwsEc2Error as e:
        flash(str(e), "error")
    return redirect(url_for("aws_ec2"))


@app.route("/aws/s3")
def aws_s3():
    try:
        buckets = s3_core.list_buckets(AWS_REGION)
        return render_template("aws_s3.html", buckets=buckets, error=None)
    except s3_core.AwsS3Error as e:
        return render_template("aws_s3.html", buckets=[], error=str(e))


@app.route("/aws/s3/<bucket_name>")
def aws_s3_objects(bucket_name):
    try:
        objects = s3_core.list_objects(bucket_name, region=AWS_REGION)
        return render_template(
            "aws_s3_objects.html", bucket_name=bucket_name, objects=objects, error=None
        )
    except s3_core.AwsS3Error as e:
        return render_template(
            "aws_s3_objects.html", bucket_name=bucket_name, objects=[], error=str(e)
        )


@app.route("/aws/settings")
def aws_settings():
    creds = aws_config.load_credentials()
    masked = ""
    if creds:
        ak = creds["access_key"]
        masked = ak[:4] + "..." + ak[-4:] if len(ak) >= 8 else "****"
    return render_template(
        "aws_settings.html",
        has_creds=bool(creds),
        masked_key=masked,
        region=(creds.get("region") if creds else AWS_REGION),
    )


@app.route("/aws/settings/save", methods=["POST"])
def aws_settings_save():
    access_key = request.form.get("access_key", "").strip()
    secret_key = request.form.get("secret_key", "").strip()
    region = request.form.get("region", "").strip() or "us-east-1"
    session_token = request.form.get("session_token", "").strip()

    if not access_key or not secret_key:
        flash("Access Key i Secret Key su obavezni.", "error")
        return redirect(url_for("aws_settings"))

    aws_config.save_credentials(access_key, secret_key, region, session_token)
    flash("AWS kredencijali sacuvani.", "success")
    return redirect(url_for("aws_settings"))


@app.route("/aws/settings/delete", methods=["POST"])
def aws_settings_delete():
    aws_config.clear_credentials()
    flash("Kredencijali obrisani — sad se koristi IAM rola / default lanac.", "info")
    return redirect(url_for("aws_settings"))


if __name__ == "__main__":
    # host="0.0.0.0" da bude dostupno i sa drugih uredjaja u mrezi, ne samo localhost
    app.run(host="0.0.0.0", port=5000, debug=True)