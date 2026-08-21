from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SseEventEncoder:
    conversation_id: str
    turn_id: str
    run_id: str
    _seq: int = field(default=0, init=False)

    def encode(self, event: str, **data: Any) -> bytes:
        self._seq += 1
        envelope = {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "seq": self._seq,
            **data,
        }
        return f"event: {event}\ndata: {json.dumps(envelope, ensure_ascii=False)}\n\n".encode(
            "utf-8"
        )
