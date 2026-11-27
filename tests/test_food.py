import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from app import create_app
from domain import Clock
from repository import JsonPetRepository


class FrozenClock(Clock):
    def now(self):
        return datetime(2026, 11, 27, tzinfo=timezone.utc)


def client_for(tmp_path):
    repository = JsonPetRepository(tmp_path / "pets.json")
    return create_app(repository, clock=FrozenClock()).test_client()


def create_pet(client, name="Clippy"):
    response = client.post("/pets", json={"name": name})
    assert response.status_code == 201
    return response.get_json()


def test_foods_restore_different_amounts_of_hunger(tmp_path):
    client = client_for(tmp_path)
    response = client.get("/foods")
    assert response.status_code == 200
    foods = response.get_json()
    restored = [food["hunger_restored"] for food in foods]
    assert len(foods) >= 8
    assert len(set(restored)) == len(restored)
    by_extension = {
        extension: food["hunger_restored"]
        for food in foods
        for extension in food["extensions"]
    }
    assert by_extension["txt"] < by_extension["docx"] < by_extension["xlsx"] < by_extension["zip"]
    assert by_extension["doc"] == by_extension["docx"]
    assert by_extension["png"] < by_extension["pdf"]


def test_feeding_a_file_uses_its_type(tmp_path):
    client = client_for(tmp_path)
    pet = create_pet(client)
    client.post(f"/pets/{pet['id']}/actions/play")
    client.post(f"/pets/{pet['id']}/actions/play")

    text = client.post(
        f"/pets/{pet['id']}/actions/eat",
        json={"file": "notes.txt"},
    )
    assert text.status_code == 200
    text_body = text.get_json()
    assert text_body["meal"] == {
        "file": "notes.txt",
        "kind": "text",
        "label": "Text file",
        "hunger_restored": 10,
    }

    other = create_pet(client, "Office")
    client.post(f"/pets/{other['id']}/actions/play")
    client.post(f"/pets/{other['id']}/actions/play")
    sheet = client.post(
        f"/pets/{other['id']}/actions/eat",
        json={"file": "budget.XLSX"},
    )
    assert sheet.status_code == 200
    sheet_body = sheet.get_json()
    assert sheet_body["meal"]["kind"] == "spreadsheet"
    assert sheet_body["meal"]["hunger_restored"] == 50
    assert sheet_body["stats"]["hunger"] < text_body["stats"]["hunger"]


def test_word_aliases_and_nested_names(tmp_path):
    client = client_for(tmp_path)
    legacy = create_pet(client, "Legacy")
    modern = create_pet(client, "Modern")
    old = client.post(f"/pets/{legacy['id']}/actions/eat", json={"file": "letter.doc"})
    new = client.post(
        f"/pets/{modern['id']}/actions/eat",
        json={"file": "folder/letter.final.docx"},
    )
    assert old.status_code == 200
    assert new.status_code == 200
    assert old.get_json()["meal"]["hunger_restored"] == new.get_json()["meal"]["hunger_restored"]
    assert old.get_json()["stats"]["hunger"] == new.get_json()["stats"]["hunger"]


def test_unknown_or_missing_file_is_rejected(tmp_path):
    client = client_for(tmp_path)
    pet = create_pet(client)
    missing = client.post(f"/pets/{pet['id']}/actions/eat", json={})
    unknown = client.post(f"/pets/{pet['id']}/actions/eat", json={"file": "virus.bat"})
    assert missing.status_code == 400
    assert unknown.status_code == 400
    assert "Unknown file type '.bat'" in unknown.get_json()["error"]
    assert client.get(f"/pets/{pet['id']}").get_json()["stats"]["hunger"] == pet["stats"]["hunger"]


def test_other_actions_still_work(tmp_path):
    client = client_for(tmp_path)
    pet = create_pet(client)
    played = client.post(f"/pets/{pet['id']}/actions/play")
    assert played.status_code == 200
    assert "meal" not in played.get_json()
    assert played.get_json()["stats"]["happiness"] > pet["stats"]["happiness"]
