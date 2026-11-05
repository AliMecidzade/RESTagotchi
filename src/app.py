from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"status": "alive", "message": "RESTagotchi API is ready!"})

@app.route("/status")
def status():
    return jsonify({"hunger": 50, "happiness": 50, "is_alive": True})

@app.route("/pet/<name>")
def pet_info(name):
    return jsonify({"message": f"Pet {name} is doing great!", "owner": "Team"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
