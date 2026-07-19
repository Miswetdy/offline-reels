from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content_type: str
    byte_size: int
    created_at: datetime
