"""Pet storage. A single JSON file for now; the interface can be swapped later."""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from domain import Pet


class PetRepository(ABC):
    @abstractmethod
    def save(self, pet: Pet) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_many(self, pets: list[Pet]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, pet_id: str) -> Pet | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> list[Pet]:
        raise NotImplementedError


class JsonPetRepository(PetRepository):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def save(self, pet: Pet) -> None:
        self.save_many([pet])

    def save_many(self, pets: list[Pet]) -> None:
        if not pets:
            return
        with self._lock:
            stored = self._read()
            for pet in pets:
                stored[pet.id] = pet
            self._write(stored)

    def get(self, pet_id: str) -> Pet | None:
        with self._lock:
            return self._read().get(pet_id)

    def list_all(self) -> list[Pet]:
        with self._lock:
            pets = list(self._read().values())
        pets.sort(key=lambda pet: (pet.created_at, pet.id))
        return pets

    def _read(self) -> dict[str, Pet]:
        if not self.path.exists():
            return {}
        text = self.path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        raw = json.loads(text)
        return {pet_id: Pet.from_dict(payload) for pet_id, payload in raw.items()}

    def _write(self, pets: dict[str, Pet]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {pet_id: pet.to_dict() for pet_id, pet in pets.items()}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
