from flask import Flask, request
from datetime import datetime
import csv
import os

app = Flask(__name__)

CSV_FILE = "dados.csv"


@app.route("/")
def home():
    return "Servidor PMCA Online"


@app.route("/dados", methods=["POST"])
def receber_dados():

    fluxo = request.form.get("fluxo")
    total = request.form.get("total")

    if fluxo is None:
        return "Erro", 400

    existe = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, "a", newline="") as arquivo:

        writer = csv.writer(arquivo)

        if not existe:
            writer.writerow(["data_hora", "fluxo_litros", "consumo_total"])

        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fluxo, total])

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
