import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from app import app

def test_index_route():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"RESTagotchi API is ready!" in response.data

def test_pet_route():
    client = app.test_client()
    response = client.get("/pet/Ali")
    assert response.status_code == 200
    assert b"Pet Ali is doing great!" in response.data

