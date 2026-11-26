import os
from pathlib import Path

from flask import Flask, jsonify, request

from domain import Clock, InvalidPetNameError, Pet, PetNotFoundError, UnknownActionError
from repository import JsonPetRepository, PetRepository
from service import PetService


def default_data_path() -> Path:
    override = os.environ.get("RESTAGOTCHI_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "pets.json"


def pet_resource(pet: Pet) -> dict:
    data = pet.to_dict()
    data["stats"] = {key: round(value, 1) for key, value in data["stats"].items()}
    return data


def create_app(
    repository: PetRepository | None = None,
    clock: Clock | None = None,
) -> Flask:
    app = Flask(__name__)
    service = PetService(repository or JsonPetRepository(default_data_path()), clock=clock)

    @app.get("/")
    def index():
        return jsonify({"status": "alive", "message": "RESTagotchi API is ready!"})

    @app.get("/actions")
    def list_actions():
        return jsonify(service.list_actions())

    @app.post("/pets")
    def create_pet():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            body = {}
        try:
            pet = service.create_pet(body.get("name", ""))
        except InvalidPetNameError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(pet_resource(pet)), 201

    @app.get("/pets")
    def list_pets():
        return jsonify([pet_resource(pet) for pet in service.list_pets()])

    @app.get("/pets/<pet_id>")
    def get_pet(pet_id):
        try:
            pet = service.get_pet(pet_id)
        except PetNotFoundError:
            return jsonify({"error": "Pet not found"}), 404
        return jsonify(pet_resource(pet))

    @app.post("/pets/<pet_id>/actions/<action_name>")
    def perform_action(pet_id, action_name):
        try:
            pet = service.perform_action(pet_id, action_name.strip().lower())
        except PetNotFoundError:
            return jsonify({"error": "Pet not found"}), 404
        except UnknownActionError:
            return jsonify({"error": "Unknown action"}), 400
        return jsonify(pet_resource(pet))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
