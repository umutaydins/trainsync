"""An in-memory `StateStore` for bot unit tests (Redis in production; TTLs are recorded, not
enforced)."""

from dataclasses import dataclass, field


@dataclass
class MemoryStateStore:
    values: dict[str, str] = field(default_factory=dict)
    ttls: dict[str, int] = field(default_factory=dict)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_s

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.ttls.pop(key, None)
