"""Lease value object and explicit lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from transitions import Machine


@dataclass
class Lease:
    role: str
    scope: str
    holder_id: int | str
    epoch: int
    start_time: float
    duration: float
    expiry_time: float
    state: str = "pending"
    renewal_fraction: float = 0.7
    machine: Machine = field(init=False, repr=False)

    STATES: ClassVar[tuple[str, ...]] = ("pending", "active", "renewing", "migrating", "expired")
    TRANSITIONS: ClassVar[list[dict[str, Any]]] = [
        {"trigger": "activate", "source": "pending", "dest": "active"},
        {"trigger": "renew", "source": "active", "dest": "renewing"},
        {"trigger": "commit_renewal", "source": "renewing", "dest": "active"},
        {"trigger": "begin_migration", "source": "active", "dest": "migrating"},
        {"trigger": "migrated", "source": "migrating", "dest": "active"},
        {"trigger": "expire", "source": "active", "dest": "expired"},
        {"trigger": "invalidate", "source": ["active", "renewing", "migrating"], "dest": "expired"},
    ]

    def __post_init__(self) -> None:
        if self.duration <= 0:
            raise ValueError("lease duration must be positive")
        if not 0 < self.renewal_fraction < 1:
            raise ValueError("renewal_fraction must be in (0, 1)")
        if self.expiry_time <= self.start_time:
            raise ValueError("lease expiry must be after its start")
        self.machine = Machine(
            model=self,
            states=self.STATES,
            transitions=self.TRANSITIONS,
            initial="pending",
            auto_transitions=False,
        )

    @property
    def renewal_time(self) -> float:
        return self.start_time + self.renewal_fraction * self.duration

    def activate_lease(self) -> None:
        self.activate()

    def renew_period(self, now: float, duration: float) -> None:
        if duration <= 0:
            raise ValueError("lease duration must be positive")
        self.renew()
        self.start_time = now
        self.duration = duration
        self.expiry_time = now + duration
        self.commit_renewal()

    def migrate_holder(self, holder_id: int | str, now: float, duration: float, epoch: int) -> None:
        if duration <= 0:
            raise ValueError("lease duration must be positive")
        self.begin_migration()
        self.holder_id = holder_id
        self.epoch = epoch
        self.start_time = now
        self.duration = duration
        self.expiry_time = now + duration
        self.migrated()

    def invalidate_lease(self) -> None:
        if self.state != "expired":
            self.invalidate()
