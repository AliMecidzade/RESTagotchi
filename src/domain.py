"""RESTagotchi domain: pet, stats, actions, and the passage of time."""

from __future__ import annotations

import uuid
from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


STAT_MIN = 0.0
STAT_MAX = 100.0
MAX_NAME_LENGTH = 30

# Hunger and fatigue kill at 100. Happiness kills at 0: that is boredom.
CAUSE_HUNGER = "hunger"
CAUSE_FATIGUE = "fatigue"
CAUSE_BOREDOM = "boredom"


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

    happiness: 0 is bored to death, 100 is happy.
    hunger: 0 is full, 100 is starved to death.
    fatigue: 0 is rested, 100 is exhausted to death.
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


def death_cause(stats: PetStats) -> str | None:
    """Which lethal extreme the stats have already reached, if any.

    Hunger and fatigue are fatal at 100. Happiness is fatal at 0 (boredom).
    When several are lethal at once, hunger wins, then fatigue, then boredom.
    """

    if stats.hunger >= STAT_MAX:
        return CAUSE_HUNGER
    if stats.fatigue >= STAT_MAX:
        return CAUSE_FATIGUE
    if stats.happiness <= STAT_MIN:
        return CAUSE_BOREDOM
    return None


class TimeDecay:
    """How stats drift on their own while the pet is left alone.

    Each real minute: happiness -1, hunger +2, fatigue +1.
    Time keeps passing while the server is off; the clock starts at updated_at.
    Drift stops at the moment a stat becomes fatal.
    """

    per_minute = Effect(happiness=-1.0, hunger=2.0, fatigue=1.0)

    def apply(self, stats: PetStats, elapsed_seconds: float) -> None:
        if elapsed_seconds <= 0:
            return
        stats.apply(self.per_minute.scaled(elapsed_seconds / 60.0))

    def time_until_death(self, stats: PetStats) -> tuple[float, str] | None:
        """Seconds until this decay kills the pet, and the cause.

        None when the rates cannot push any stat into a lethal extreme.
        """

        candidates: list[tuple[float, int, str]] = []

        def consider(
            current: float,
            per_minute: float,
            lethal: float,
            cause: str,
            priority: int,
        ) -> None:
            already_there = (lethal == STAT_MAX and current >= STAT_MAX) or (
                lethal == STAT_MIN and current <= STAT_MIN
            )
            if already_there:
                candidates.append((0.0, priority, cause))
                return
            if per_minute == 0:
                return
            minutes = (lethal - current) / per_minute
            if minutes < 0:
                return
            candidates.append((minutes * 60.0, priority, cause))

        consider(stats.hunger, self.per_minute.hunger, STAT_MAX, CAUSE_HUNGER, 0)
        consider(stats.fatigue, self.per_minute.fatigue, STAT_MAX, CAUSE_FATIGUE, 1)
        consider(stats.happiness, self.per_minute.happiness, STAT_MIN, CAUSE_BOREDOM, 2)
        if not candidates:
            return None
        seconds, _, cause = min(candidates)
        return seconds, cause


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
        is_alive: bool = True,
        cause_of_death: str | None = None,
        died_at: datetime | None = None,
    ) -> None:
        self.id = pet_id
        self.name = name
        self.stats = stats
        self.created_at = created_at
        self.updated_at = updated_at
        self.decay = decay or TimeDecay()
        self.is_alive = is_alive
        self.cause_of_death = cause_of_death
        self.died_at = died_at

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
        if not self.is_alive:
            return
        elapsed = (now - self.updated_at).total_seconds()
        if elapsed < 0:
            return
        until_death = self.decay.time_until_death(self.stats)
        if until_death is not None:
            seconds, cause = until_death
            if seconds <= elapsed:
                self.decay.apply(self.stats, seconds)
                self.die(cause, self.updated_at + timedelta(seconds=seconds))
                return
        if elapsed == 0:
            return
        self.decay.apply(self.stats, elapsed)
        self.updated_at = now
        cause = death_cause(self.stats)
        if cause is not None:
            self.die(cause, now)

    def perform(self, action: Action, now: datetime) -> None:
        self.tick(now)
        if not self.is_alive:
            raise PetDeadError(self)
        action.apply(self.stats)
        self.updated_at = now
        cause = death_cause(self.stats)
        if cause is not None:
            self.die(cause, now)

    def die(self, cause: str, when: datetime) -> None:
        if not self.is_alive:
            return
        if cause == CAUSE_HUNGER:
            self.stats.hunger = STAT_MAX
        elif cause == CAUSE_FATIGUE:
            self.stats.fatigue = STAT_MAX
        elif cause == CAUSE_BOREDOM:
            self.stats.happiness = STAT_MIN
        self.is_alive = False
        self.cause_of_death = cause
        self.died_at = when
        self.updated_at = when

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "stats": self.stats.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_alive": self.is_alive,
            "cause_of_death": self.cause_of_death,
            "died_at": self.died_at.isoformat() if self.died_at is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Pet:
        died_at = data.get("died_at")
        return cls(
            pet_id=str(data["id"]),
            name=str(data["name"]),
            stats=PetStats.from_dict(data["stats"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            is_alive=bool(data.get("is_alive", True)),
            cause_of_death=data.get("cause_of_death"),
            died_at=datetime.fromisoformat(died_at) if died_at else None,
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


class PetDeadError(RuntimeError):
    def __init__(self, pet: Pet) -> None:
        self.pet = pet
        super().__init__(pet.cause_of_death or "dead")


class UnknownActionError(ValueError):
    def __init__(self, action_name: str) -> None:
        self.action_name = action_name
        super().__init__(action_name)
