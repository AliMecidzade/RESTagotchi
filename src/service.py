"""Use cases: create a pet, read it with elapsed time applied, and perform an action."""

from __future__ import annotations

from domain import ACTIONS, Clock, Pet, PetNotFoundError, get_action
from repository import PetRepository


class PetService:
    def __init__(self, repository: PetRepository, clock: Clock | None = None) -> None:
        self.repository = repository
        self.clock = clock or Clock()

    def create_pet(self, name: str) -> Pet:
        pet = Pet.create(name, self.clock.now())
        self.repository.save(pet)
        return pet

    def get_pet(self, pet_id: str) -> Pet:
        pet = self._require(pet_id)
        pet.tick(self.clock.now())
        self.repository.save(pet)
        return pet

    def list_pets(self) -> list[Pet]:
        now = self.clock.now()
        pets = self.repository.list_all()
        for pet in pets:
            pet.tick(now)
        self.repository.save_many(pets)
        return pets

    def perform_action(self, pet_id: str, action_name: str) -> Pet:
        pet = self._require(pet_id)
        action = get_action(action_name)
        pet.perform(action, self.clock.now())
        self.repository.save(pet)
        return pet

    def list_actions(self) -> list[dict]:
        return [action.to_dict() for action in ACTIONS.values()]

    def _require(self, pet_id: str) -> Pet:
        pet = self.repository.get(pet_id)
        if pet is None:
            raise PetNotFoundError(pet_id)
        return pet
