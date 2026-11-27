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


@dataclass(frozen=True)
class Food:
    """A file Clippy can eat. The extension decides how much hunger it restores.

    hunger_restored is how far the hunger stat falls (0 is full, 100 is starving).
    """

    kind: str
    label: str
    extensions: tuple[str, ...]
    hunger_restored: float
    happiness: float = 0.0
    fatigue: float = 0.0

    def __post_init__(self) -> None:
        if self.hunger_restored < 0:
            raise ValueError("hunger_restored must be zero or positive")
        if not self.extensions:
            raise ValueError("food needs at least one extension")

    @property
    def effect(self) -> Effect:
        return Effect(
            happiness=self.happiness,
            hunger=-self.hunger_restored,
            fatigue=self.fatigue,
        )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "extensions": list(self.extensions),
            "hunger_restored": self.hunger_restored,
            "effects": self.effect.to_dict(),
        }


# Light files barely help. Office documents are a real meal. An archive is a feast.
FOOD_CATALOG: tuple[Food, ...] = (
    Food("image", "Image", ("png", "jpg", "jpeg", "gif", "webp"), 8, happiness=18, fatigue=1),
    Food("text", "Text file", ("txt",), 10, happiness=3, fatigue=1),
    Food("markdown", "Markdown note", ("md",), 14, happiness=5, fatigue=1),
    Food("program", "Program", ("exe",), 15, happiness=-12, fatigue=16),
    Food("json", "JSON file", ("json",), 18, happiness=4, fatigue=2),
    Food("csv", "CSV table", ("csv",), 20, happiness=3, fatigue=2),
    Food("html", "Web page", ("html", "htm"), 22, happiness=7, fatigue=2),
    Food("javascript", "JavaScript file", ("js",), 24, happiness=8, fatigue=3),
    Food("python", "Python script", ("py",), 26, happiness=9, fatigue=3),
    Food("presentation", "PowerPoint deck", ("ppt", "pptx"), 34, happiness=16, fatigue=5),
    Food("word", "Word document", ("doc", "docx"), 40, happiness=12, fatigue=4),
    Food("pdf", "PDF", ("pdf",), 44, happiness=6, fatigue=8),
    Food("spreadsheet", "Excel workbook", ("xls", "xlsx"), 50, happiness=8, fatigue=6),
    Food("archive", "Archive", ("zip", "rar", "7z"), 62, happiness=4, fatigue=14),
)

FOOD_BY_EXTENSION: dict[str, Food] = {
    extension: food
    for food in FOOD_CATALOG
    for extension in food.extensions
}


def file_extension(filename: str) -> str:
    """Extension of a file name, or the bare type when no dot is present."""

    if not isinstance(filename, str):
        raise FoodError("File name must be a string")
    token = filename.strip().lower()
    if not token:
        raise FoodError("Choose a file to feed Clippy")
    if token.startswith(".") and token.count(".") == 1:
        token = token[1:]
    elif "." in token:
        token = token.rsplit(".", 1)[-1]
    if not token or not token.isascii() or not token.isalnum():
        raise FoodError("File needs an extension Clippy can eat")
    return token


def resolve_food(filename: str) -> Food:
    extension = file_extension(filename)
    food = FOOD_BY_EXTENSION.get(extension)
    if food is None:
        raise FoodError(f"Unknown file type '.{extension}'")
    return food


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
    """Feed Clippy a file. How much hunger it restores depends on the extension."""

    name = "eat"
    label = "Eat"
    effect = Effect()

    def __init__(self, food: Food | None = None, filename: str = "") -> None:
        self.food = food
        self.filename = filename
        if food is not None:
            self.effect = food.effect

    def apply(self, stats: PetStats) -> None:
        if self.food is None:
            raise FoodError("Choose a file to feed Clippy")
        super().apply(stats)

    def to_dict(self) -> dict:
        if self.food is None:
            return {
                "name": self.name,
                "label": self.label,
                "description": (
                    'Feed Clippy a file, for example {"file": "notes.docx"}. '
                    "Hunger restored depends on the extension. See GET /foods."
                ),
            }
        payload = super().to_dict()
        payload["file"] = self.filename
        payload["food"] = self.food.kind
        payload["hunger_restored"] = self.food.hunger_restored
        return payload

    def meal_dict(self) -> dict:
        if self.food is None:
            raise FoodError("Choose a file to feed Clippy")
        return {
            "file": self.filename,
            "kind": self.food.kind,
            "label": self.food.label,
            "hunger_restored": self.food.hunger_restored,
        }


def eat_file(filename: str | None) -> EatAction:
    if filename is None or (isinstance(filename, str) and not filename.strip()):
        raise FoodError("Choose a file to feed Clippy")
    food = resolve_food(filename)
    display_name = filename.strip() if isinstance(filename, str) else filename
    return EatAction(food, display_name)


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


class FoodError(ValueError):
    """The file cannot be fed to Clippy."""


class PetNotFoundError(LookupError):
    def __init__(self, pet_id: str) -> None:
        self.pet_id = pet_id
        super().__init__(pet_id)


class UnknownActionError(ValueError):
    def __init__(self, action_name: str) -> None:
        self.action_name = action_name
        super().__init__(action_name)
