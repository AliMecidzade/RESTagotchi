import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from app import create_app
from domain import Clock, Pet, PetStats
from repository import JsonPetRepository


class ManualClock(Clock):
    def __init__(self):
        self.current = datetime(2026, 11, 28, tzinfo=timezone.utc)

    def now(self):
        return self.current

    def advance(self, **kwargs):
        self.current += timedelta(**kwargs)


def client_for(tmp_path, clock, pets=()):
    repository = JsonPetRepository(tmp_path / "pets.json")
    for pet in pets:
        repository.save(pet)
    return create_app(repository, clock=clock).test_client()


def create_pet(client, name="Clippy"):
    response = client.post("/pets", json={"name": name})
    assert response.status_code == 201
    body = response.get_json()
    assert body["is_alive"] is True
    assert body["cause_of_death"] is None
    assert body["died_at"] is None
    return body


def test_neglect_kills_by_hunger_and_then_time_stops(tmp_path):
    clock = ManualClock()
    client = client_for(tmp_path, clock)
    pet = create_pet(client)

    clock.advance(minutes=34)
    still_alive = client.get(f"/pets/{pet['id']}").get_json()
    assert still_alive["is_alive"] is True
    assert still_alive["stats"]["hunger"] == 98

    clock.advance(minutes=1)
    dead = client.get(f"/pets/{pet['id']}").get_json()
    assert dead["is_alive"] is False
    assert dead["cause_of_death"] == "hunger"
    assert dead["stats"] == {"happiness": 45, "hunger": 100, "fatigue": 55}
    assert dead["died_at"] == dead["updated_at"]

    clock.advance(hours=5)
    later = client.get(f"/pets/{pet['id']}").get_json()
    assert later["stats"] == dead["stats"]
    assert later["died_at"] == dead["died_at"]
    assert later["updated_at"] == dead["updated_at"]

    refused = client.post(f"/pets/{pet['id']}/actions/play")
    assert refused.status_code == 409
    body = refused.get_json()
    assert body["error"] == "Pet is dead"
    assert body["cause_of_death"] == "hunger"
    assert body["pet"]["stats"] == dead["stats"]


def test_play_can_kill_from_exhaustion(tmp_path):
    clock = ManualClock()
    client = client_for(tmp_path, clock)
    pet = create_pet(client)

    for _ in range(3):
        response = client.post(f"/pets/{pet['id']}/actions/play")
        assert response.status_code == 200
        assert response.get_json()["is_alive"] is True

    killing = client.post(f"/pets/{pet['id']}/actions/play")
    assert killing.status_code == 200
    body = killing.get_json()
    assert body["is_alive"] is False
    assert body["cause_of_death"] == "fatigue"
    assert body["stats"]["fatigue"] == 100
    assert body["stats"]["hunger"] == 90

    assert client.post(f"/pets/{pet['id']}/actions/sleep").status_code == 409
    assert client.post(f"/pets/{pet['id']}/actions/unknown").status_code == 409


def test_sleeping_while_starving_kills(tmp_path):
    clock = ManualClock()
    now = clock.now()
    pet = Pet("sleepy", "Sleepy", PetStats(happiness=50, hunger=95, fatigue=40), now, now)
    client = client_for(tmp_path, clock, pets=[pet])

    response = client.post("/pets/sleepy/actions/sleep")
    assert response.status_code == 200
    body = response.get_json()
    assert body["is_alive"] is False
    assert body["cause_of_death"] == "hunger"
    assert body["stats"]["hunger"] == 100
    assert body["stats"]["fatigue"] == 0


def test_a_miserable_meal_kills_from_boredom(tmp_path):
    clock = ManualClock()
    now = clock.now()
    pet = Pet("sad", "Sad", PetStats(happiness=10, hunger=0, fatigue=0), now, now)
    client = client_for(tmp_path, clock, pets=[pet])

    response = client.post("/pets/sad/actions/eat", json={"file": "setup.exe"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["meal"]["kind"] == "program"
    assert body["is_alive"] is False
    assert body["cause_of_death"] == "boredom"
    assert body["stats"]["happiness"] == 0
    assert body["stats"]["fatigue"] == 16

    again = client.post("/pets/sad/actions/eat", json={"file": "notes.txt"})
    assert again.status_code == 409
    assert again.get_json()["pet"]["stats"]["happiness"] == 0


def test_the_stat_that_hits_first_is_the_cause(tmp_path):
    clock = ManualClock()
    now = clock.now()
    pet = Pet("tired", "Tired", PetStats(happiness=50, hunger=10, fatigue=98), now, now)
    client = client_for(tmp_path, clock, pets=[pet])

    clock.advance(minutes=10)
    body = client.get("/pets/tired").get_json()
    assert body["cause_of_death"] == "fatigue"
    assert body["stats"] == {"happiness": 48, "hunger": 14, "fatigue": 100}
    assert body["died_at"] == (now + timedelta(minutes=2)).isoformat()


def test_boredom_from_being_left_alone(tmp_path):
    clock = ManualClock()
    now = clock.now()
    pet = Pet("lonely", "Lonely", PetStats(happiness=5, hunger=0, fatigue=0), now, now)
    client = client_for(tmp_path, clock, pets=[pet])

    clock.advance(minutes=30)
    body = client.get("/pets/lonely").get_json()
    assert body["cause_of_death"] == "boredom"
    assert body["stats"] == {"happiness": 0, "hunger": 10, "fatigue": 5}
    assert body["died_at"] == (now + timedelta(minutes=5)).isoformat()


def test_time_can_kill_before_an_action_lands(tmp_path):
    clock = ManualClock()
    now = clock.now()
    pet = Pet("hungry", "Hungry", PetStats(happiness=80, hunger=99, fatigue=20), now, now)
    client = client_for(tmp_path, clock, pets=[pet])

    clock.advance(seconds=30)
    refused = client.post("/pets/hungry/actions/play")
    assert refused.status_code == 409
    stats = refused.get_json()["pet"]["stats"]
    assert stats["hunger"] == 100
    assert stats["happiness"] == 79.5
    assert refused.get_json()["cause_of_death"] == "hunger"


def test_old_saves_without_life_fields_stay_alive(tmp_path):
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    path = tmp_path / "pets.json"
    path.write_text(
        json.dumps(
            {
                "legacy": {
                    "id": "legacy",
                    "name": "Old",
                    "stats": {"happiness": 80, "hunger": 30, "fatigue": 20},
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )
    clock = ManualClock()
    client = create_app(JsonPetRepository(path), clock=clock).test_client()
    body = client.get("/pets/legacy").get_json()
    assert body["is_alive"] is True
    assert body["cause_of_death"] is None
    assert body["died_at"] is None
    assert body["stats"]["hunger"] == 30
