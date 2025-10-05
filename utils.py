import hashlib
import json
from pydantic import BaseModel
from typing import Optional, Dict, Any


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


class Message(BaseModel):
    type: str
    status: Optional[str] = None  # "ok" / "error" (response only)
    message: Optional[str] = None  # human-readable
    data: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return self.model_dump(exclude_unset=True)
