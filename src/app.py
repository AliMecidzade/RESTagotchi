import os
from pathlib import Path

from flask import Flask, jsonify, request

from domain import (
    Clock,
    FoodError,
    InvalidPetNameError,
    Pet,
    PetDeadError,
    PetNotFoundError,
    UnknownActionError,
)
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

    @app.get("/status")
    def status():
        return jsonify({"hunger": 50, "happiness": 50, "is_alive": True})

    @app.get("/pet/<name>")
    def pet_info(name):
        return jsonify({"message": f"Pet {name} is doing great!", "owner": "Team"})

    @app.get("/actions")
    def list_actions():
        return jsonify(service.list_actions())

    @app.get("/foods")
    def list_foods():
        return jsonify(service.list_foods())

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
        body = request.get_json(silent=True)
        filename = body.get("file") if isinstance(body, dict) else None
        try:
            pet, meal = service.perform_action(
                pet_id,
                action_name.strip().lower(),
                filename=filename,
            )
        except PetNotFoundError:
            return jsonify({"error": "Pet not found"}), 404
        except PetDeadError as exc:
            return jsonify(
                {
                    "error": "Pet is dead",
                    "cause_of_death": exc.pet.cause_of_death,
                    "pet": pet_resource(exc.pet),
                }
            ), 409
        except UnknownActionError:
            return jsonify({"error": "Unknown action"}), 400
        except FoodError as exc:
            return jsonify({"error": str(exc)}), 400
        payload = pet_resource(pet)
        if meal is not None:
            payload["meal"] = meal
        return jsonify(payload)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
