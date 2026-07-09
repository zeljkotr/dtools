"""
webapp/app.py

Flask web frontend za dtool monitoring modul.
Koristi ISTU core.py logiku kao CLI (modules/monitoring/cli.py) -
nema duplirane logike, samo drugaciji prikaz.

Pokretanje:
    cd dtool
    python3 webapp/app.py
Otvori u browseru: http://localhost:5000  (ili http://IP_SERVERA:5000)
"""

import sys
import os

# Da bismo mogli da importujemo "config" i "modules" iz root foldera projekta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, render_template, request, redirect, url_for, flash
from modules.monitoring import core

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
        address = request.form.get("address")
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


@app.route("/target/<int:target_id>")
def target_details(target_id):
    t = core.get_target(target_id)
    if not t:
        flash("Target ne postoji.", "error")
        return redirect(url_for("dashboard"))
    return render_template("target_details.html", t=t)


if __name__ == "__main__":
    # host="0.0.0.0" da bude dostupno i sa drugih uredjaja u mrezi, ne samo localhost
    app.run(host="0.0.0.0", port=5000, debug=True)
