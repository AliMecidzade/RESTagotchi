"""Use cases: create a pet, read it with elapsed time applied, and perform an action."""

from __future__ import annotations

from domain import (
    ACTIONS,
    FOOD_CATALOG,
    Clock,
    EatAction,
    Pet,
    PetDeadError,
    PetNotFoundError,
    eat_file,
    get_action,
)
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

    def perform_action(
        self,
        pet_id: str,
        action_name: str,
        filename: str | None = None,
    ) -> tuple[Pet, dict | None]:
        pet = self._require(pet_id)
        if not pet.is_alive:
            raise PetDeadError(pet)
        meal = None
        if action_name == EatAction.name:
            action = eat_file(filename)
            meal = action.meal_dict()
        else:
            action = get_action(action_name)
        try:
            pet.perform(action, self.clock.now())
        except PetDeadError:
            self.repository.save(pet)
            raise
        self.repository.save(pet)
        return pet, meal

    def list_actions(self) -> list[dict]:
        return [action.to_dict() for action in ACTIONS.values()]

    def list_foods(self) -> list[dict]:
        return [food.to_dict() for food in FOOD_CATALOG]

    def _require(self, pet_id: str) -> Pet:
        pet = self.repository.get(pet_id)
        if pet is None:
            raise PetNotFoundError(pet_id)
        return pet
