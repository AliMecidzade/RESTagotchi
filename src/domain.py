"""RESTagotchi domain: pet, stats, actions, and the passage of time."""

from __future__ import annotations

import uuid
from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timezone


STAT_MIN = 0.0
STAT_MAX = 100.0
MAX_NAME_LENGTH = 30


def clamp_stat(value: float) -> float:
    return max(STAT_MIN, min(STAT_MAX, float(value)))


@dataclass(frozen=True)
class Effect:
    """How far to shift each stat. A negative value lowers it."""

    happiness: float = 0.0
    hunger: float = 0.0
    fatigue: float = 0.0

    def scaled(self, factor: float) -> Effect:
        return Effect(
            happiness=self.happiness * factor,
            hunger=self.hunger * factor,
            fatigue=self.fatigue * factor,
        )

    def to_dict(self) -> dict:
        return {
            "happiness": self.happiness,
            "hunger": self.hunger,
            "fatigue": self.fatigue,
        }


@dataclass
class PetStats:
    """Pet stats, each in the range 0..100.

    happiness: 0 is miserable, 100 is happy.
    hunger: 0 is full, 100 is starving.
    fatigue: 0 is rested, 100 is exhausted.
    """

    happiness: float = 80.0
    hunger: float = 30.0
    fatigue: float = 20.0

    def __post_init__(self) -> None:
        self.happiness = clamp_stat(self.happiness)
        self.hunger = clamp_stat(self.hunger)
        self.fatigue = clamp_stat(self.fatigue)

    def apply(self, effect: Effect) -> None:
        self.happiness = clamp_stat(self.happiness + effect.happiness)
        self.hunger = clamp_stat(self.hunger + effect.hunger)
        self.fatigue = clamp_stat(self.fatigue + effect.fatigue)

    def to_dict(self) -> dict:
        return {
            "happiness": self.happiness,
            "hunger": self.hunger,
            "fatigue": self.fatigue,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PetStats:
        return cls(
            happiness=float(data["happiness"]),
            hunger=float(data["hunger"]),
            fatigue=float(data["fatigue"]),
        )


class TimeDecay:
    """How stats drift on their own while the pet is left alone.

    Each real minute: happiness -1, hunger +2, fatigue +1.
    Time keeps passing while the server is off; the clock starts at updated_at.
    """

    per_minute = Effect(happiness=-1.0, hunger=2.0, fatigue=1.0)

    def apply(self, stats: PetStats, elapsed_seconds: float) -> None:
        if elapsed_seconds <= 0:
            return
        stats.apply(self.per_minute.scaled(elapsed_seconds / 60.0))


class Action(ABC):
    """An instant action performed on a pet."""

    name: str
    label: str
    effect: Effect

    def apply(self, stats: PetStats) -> None:
        stats.apply(self.effect)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "effects": self.effect.to_dict(),
        }


class EatAction(Action):
    """Eat: hunger drops sharply and mood rises a little."""

    name = "eat"
    label = "Eat"
    effect = Effect(happiness=10, hunger=-40, fatigue=5)


class PlayAction(Action):
    """Have fun: happiness rises, and so do hunger and fatigue."""

    name = "play"
    label = "Have fun"
    effect = Effect(happiness=25, hunger=15, fatigue=20)


class SleepAction(Action):
    """Sleep: fatigue drops, and the pet gets a little hungry while resting."""

    name = "sleep"
    label = "Sleep"
    effect = Effect(happiness=5, hunger=10, fatigue=-50)


ACTIONS: dict[str, Action] = {
    EatAction.name: EatAction(),
    PlayAction.name: PlayAction(),
    SleepAction.name: SleepAction(),
}


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class Pet:
    def __init__(
        self,
        pet_id: str,
        name: str,
        stats: PetStats,
        created_at: datetime,
        updated_at: datetime,
        decay: TimeDecay | None = None,
    ) -> None:
        self.id = pet_id
        self.name = name
        self.stats = stats
        self.created_at = created_at
        self.updated_at = updated_at
        self.decay = decay or TimeDecay()

    @classmethod
    def create(cls, name: str, now: datetime) -> Pet:
        return cls(
            pet_id=uuid.uuid4().hex,
            name=normalize_name(name),
            stats=PetStats(),
            created_at=now,
            updated_at=now,
        )

    def tick(self, now: datetime) -> None:
        elapsed = (now - self.updated_at).total_seconds()
        self.decay.apply(self.stats, elapsed)
        if elapsed > 0:
            self.updated_at = now

    def perform(self, action: Action, now: datetime) -> None:
        self.tick(now)
        action.apply(self.stats)
        self.updated_at = now

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "stats": self.stats.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Pet:
        return cls(
            pet_id=str(data["id"]),
            name=str(data["name"]),
            stats=PetStats.from_dict(data["stats"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        raise InvalidPetNameError("Pet name must be a string")
    clean = " ".join(name.split())
    if not clean:
        raise InvalidPetNameError("Pet name cannot be empty")
    if len(clean) > MAX_NAME_LENGTH:
        raise InvalidPetNameError("Pet name cannot be longer than 30 characters")
    return clean


def get_action(name: str) -> Action:
    action = ACTIONS.get(name)
    if action is None:
        raise UnknownActionError(name)
    return action


class InvalidPetNameError(ValueError):
    pass


class PetNotFoundError(LookupError):
    def __init__(self, pet_id: str) -> None:
        self.pet_id = pet_id
        super().__init__(pet_id)


class UnknownActionError(ValueError):
    def __init__(self, action_name: str) -> None:
        self.action_name = action_name
        super().__init__(action_name)
