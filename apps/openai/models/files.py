import logging
import time
from typing import List, Literal
from uuid import uuid4

from openai.types import FileObject as FileModel
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, BigInteger, Text, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship, Mapped, mapped_column

from apps.openai.internal.db import JSONField, Base, get_db

log = logging.getLogger(__name__)


####################
# Files DB Schema
####################


class File(Base):
    __tablename__ = "file"

    id = Column(String, primary_key=True)
    object = Column(String, nullable=False)
    bytes = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    filename = Column(Text, nullable=False)
    purpose = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    status_details = Column(Text, nullable=True)
    meta = Column(JSONField, nullable=True)

    file_content: Mapped["FileContent"] = relationship(back_populates="file")


class FileContent(Base):
    __tablename__ = "file_content"

    content = Column(LargeBinary, nullable=False)
    file_id: Mapped[String] = mapped_column(ForeignKey("file.id", ondelete="CASCADE"),
                                            primary_key=True, nullable=False)
    file: Mapped["File"] = relationship(back_populates="file_content")


####################
# Models
####################

class FileContentModel(BaseModel):
    file_id: str
    content: bytes

    model_config = ConfigDict(from_attributes=True)


class FilesTable:

    def create_file(self, purpose: str, filename: str, file_bytes: bytes) -> FileModel | None:
        form_data = FileModel(
            id=str(uuid4()),
            bytes=len(file_bytes),
            created_at=int(time.time()),
            filename=filename,
            object="file",
            status="uploaded",
            purpose=purpose
        )
        try:
            with get_db() as db:
                result = File(**form_data.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FileModel.model_validate(result, from_attributes=True)
                else:
                    return None
        except Exception as e:
            print(f"Error inserting new file: {e}")
            return None

    def get_file(self, file_id: str) -> FileModel:
        with get_db() as db:
            file = db.get(File, file_id)
            return FileModel.model_validate(file, from_attributes=True)

    def get_files(self, purpose: str | None) -> List[FileModel]:
        try:
            with get_db() as db:
                if purpose:
                    return [FileModel.model_validate(file)
                            for file in db.query(File).filter_by(purpose=purpose)]
                else:
                    return [FileModel.model_validate(file, from_attributes=True) for file in db.query(File).all()]
        except Exception as e:
            print(f"Error getting files: {e}")
            return []

    def delete_file(self, file_id: str) -> bool:
        try:
            with get_db() as db:
                deleted_files_count = db.query(File).filter_by(id=file_id).delete()
                db.commit()
                if deleted_files_count > 0:
                    return True
                return False
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False


Files = FilesTable()


class FileContentsTable:

    def create_file_content(self, file_id: str, content: bytes) -> FileContentModel | None:
        model = FileContentModel(file_id=file_id, content=content)

        try:
            result = FileContent(**model.model_dump())
            with get_db() as db:
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FileContentModel.model_validate(result, from_attributes=True)
                else:
                    return None
        except Exception as e:
            print(f"Error creating file content: {e}")
            return None

    def get_file_content(self, file_id: str) -> bytes | None:
        try:
            with get_db() as db:
                file_content = db.get(FileContent, file_id)
                return file_content.content
        except Exception as e:
            print(f"Error getting file content: {e}")
            return None


FileContents = FileContentsTable()
