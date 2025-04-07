from typing import Optional
import os
import uuid
from datetime import datetime

from app.core.config import settings

class VoiceService:
    def __init__(self):
        self.upload_dir = os.path.join(settings.UPLOAD_DIR, "voice")
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_voice_file(self, file_content: bytes, file_name: str) -> str:
        file_path = os.path.join(self.upload_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(file_content)
        return file_path

    def delete_voice_file(self, file_path: str) -> None:
        if os.path.exists(file_path):
            os.remove(file_path)

    def get_file_path(self, file_name: str) -> str:
        return os.path.join(self.upload_dir, file_name)

voice_service = VoiceService() 