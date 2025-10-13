import hashlib
import secrets
from pydantic import BaseModel
from typing import Optional, Dict, Any


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def generate_salt() -> str:
    return secrets.token_hex(16)


class Message(BaseModel):
    type: str
    status: Optional[str] = None  # "ok" / "error" (response only)
    message: Optional[str] = None  # human-readable
    data: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return self.model_dump(exclude_unset=True)
