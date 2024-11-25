import logging
import time
from typing import List, Type, Literal
from uuid import uuid4

from openai.types.beta.vector_store import ExpiresAfter as ExpiresAfterModel
from openai.types.beta.vector_store import FileCounts as FileCountsModel
from openai.types.beta.vector_store import VectorStore as VectorStoreModel
from openai.types.beta.vector_stores import VectorStoreFile as VectorStoreFileModel
from openai.types.beta.vector_stores.vector_store_file import ChunkingStrategyOther as ChunkingStrategyOtherModel
from openai.types.beta.vector_stores.vector_store_file import ChunkingStrategyStatic as ChunkingStrategyStaticModel
from openai.types.beta.vector_stores.vector_store_file import \
    ChunkingStrategyStaticStatic as ChunkingStrategyStaticStaticModel
from openai.types.beta.vector_stores.vector_store_file import LastError as LastErrorModel
from pydantic import BaseModel
from sqlalchemy import Column, String, BigInteger, Text, ForeignKey, UnaryExpression
from sqlalchemy.orm import relationship, Mapped, mapped_column

from apps.openai.internal.db import JSONField, Base, get_db

log = logging.getLogger(__name__)


class VectorStore(Base):
    __tablename__ = "vector_store"

    id = Column(String, primary_key=True)
    created_at = Column(BigInteger, nullable=False)
    last_active_at = Column(BigInteger, nullable=False)
    meta = Column("metadata", JSONField, nullable=True)
    name = Column(Text, nullable=True)
    object = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    usage_bytes = Column(BigInteger, nullable=False)
    expires_at = Column(BigInteger, nullable=True)
    expires_after: Mapped["ExpiresAfter"] = relationship(back_populates="vector_store")
    file_counts: Mapped["FileCounts"] = relationship(back_populates="vector_store")
    vector_store_files: Mapped[List["VectorStoreFile"]] = relationship(back_populates="vector_store")


class VectorStoreFile(Base):
    __tablename__ = "vector_store_file"

    id = Column(String, primary_key=True)
    object = Column(Text, nullable=False)
    usage_bytes = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    vector_store_id: Mapped[String] = mapped_column(ForeignKey("vector_store.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False)
    last_error: Mapped["LastError"] = relationship(back_populates="vector_store_file")
    chunking_strategy: Mapped["ChunkingStrategy"] = relationship(back_populates="vector_store_file")

    file_id = Column(String, ForeignKey("file.id", ondelete='CASCADE'), nullable=False)
    vector_store: Mapped["VectorStore"] = relationship(back_populates="vector_store_files")


class LastError(Base):
    __tablename__ = "last_error"
    code = Column(Text, nullable=True)
    message = Column(Text, nullable=True)

    vector_store_file_id: Mapped[String] = mapped_column(ForeignKey("vector_store_file.id", ondelete="CASCADE"),
                                                         primary_key=True)
    vector_store_file: Mapped["VectorStoreFile"] = relationship(back_populates="last_error")


class ChunkingStrategy(Base):
    __tablename__ = "chunking_strategy"

    static: Mapped["ChunkingStrategyStatic"] = relationship(back_populates="chunking_strategy")
    type = Column(Text, nullable=True)

    vector_store_file_id: Mapped[String] = mapped_column(ForeignKey("vector_store_file.id", ondelete="CASCADE"),
                                                         primary_key=True)
    vector_store_file: Mapped["VectorStoreFile"] = relationship(back_populates="chunking_strategy")


class ChunkingStrategyStatic(Base):
    __tablename__ = "chunking_strategy_static"

    chunk_overlap_tokens = Column(BigInteger, nullable=True)
    max_chunk_size_tokens = Column(BigInteger, nullable=True)

    chunking_strategy_id: Mapped[String] = mapped_column(
        ForeignKey("chunking_strategy.vector_store_file_id", ondelete="CASCADE"),
        primary_key=True)
    chunking_strategy: Mapped["ChunkingStrategy"] = relationship(back_populates="static")


class ExpiresAfter(Base):
    __tablename__ = "vector_store_expires_after"
    days = Column(BigInteger, nullable=True)
    anchor = Column(Text, nullable=True)
    vector_store_id: Mapped[String] = mapped_column(ForeignKey("vector_store.id", ondelete='CASCADE'), primary_key=True)
    vector_store: Mapped["VectorStore"] = relationship(back_populates="expires_after")


class FileCounts(Base):
    __tablename__ = "vector_store_file_counts"
    in_progress = Column(BigInteger, nullable=False)
    completed = Column(BigInteger, nullable=False)
    failed = Column(BigInteger, nullable=False)
    cancelled = Column(BigInteger, nullable=False)
    total = Column(BigInteger, nullable=False)
    vector_store_id: Mapped[String] = mapped_column(ForeignKey("vector_store.id", ondelete='CASCADE'), primary_key=True)
    vector_store: Mapped["VectorStore"] = relationship(back_populates="file_counts")


####################
# Models
####################

VectorStoreModel.model_validate_original = VectorStoreModel.model_validate


def model_validate_custom_metadata_mapping(vector_store: VectorStore) -> VectorStoreModel:
    model = VectorStoreModel.model_validate_original(vector_store, from_attributes=True)
    model.metadata = vector_store.meta
    return model


VectorStoreModel.model_validate = model_validate_custom_metadata_mapping


####################
# Forms
####################


class VectorStoreForm(BaseModel):
    id: str
    filename: str
    meta: dict = {}


class StaticForm(BaseModel):
    max_chunk_size_tokens: int
    chunk_overlap_tokens: int


class AutoChunkingStrategyForm(BaseModel):
    type: str = Literal["auto"]


class StaticChunkingStrategyForm(BaseModel):
    type: str = Literal["static"]
    static: StaticForm


class ExpiresAfterForm(BaseModel):
    anchor: str
    days: int


class CreateVectorStoreForm(BaseModel):
    file_ids: list[str] | None = None
    name: str | None = None
    chunking_strategy: StaticChunkingStrategyForm | AutoChunkingStrategyForm | None = None
    metadata: dict | None = None
    expires_after: ExpiresAfterForm | None = None


class CreateVectorStoreFileForm(BaseModel):
    file_id: str
    chunking_strategy: StaticChunkingStrategyForm | AutoChunkingStrategyForm | None = None


class ModifyVectorStoreForm(BaseModel):
    name: str | None = None
    expires_after: ExpiresAfterForm | None = None
    metadata: dict | None = None


class VectorStoresTable:

    def create_vector_store(self, form_data: CreateVectorStoreForm) -> VectorStoreModel | None:
        try:
            anchor = None
            days = None
            if form_data.expires_after:
                anchor = form_data.expires_after.anchor
                days = form_data.expires_after.days

            model = VectorStoreModel(
                id=str(uuid4()),
                created_at=int(time.time()),
                file_counts=FileCountsModel(cancelled=0,
                                            completed=0,
                                            failed=0,
                                            in_progress=0,
                                            total=0),
                last_active_at=int(time.time()),
                metadata=form_data.metadata,
                name=form_data.name,
                object="vector_store",
                status="completed",
                usage_bytes=0,
                expires_after=ExpiresAfterModel(anchor=anchor, days=days) if anchor else None,
            )

            result = VectorStore(**model.model_dump(exclude={"file_counts", "expires_after", "metadata"}),
                                 expires_after=ExpiresAfter(
                                     **model.expires_after.model_dump()) if model.expires_after else None,
                                 file_counts=FileCounts(**model.file_counts.model_dump()),
                                 meta=model.metadata
                                 )
            with get_db() as db:
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return VectorStoreModel.model_validate(result)
                else:
                    return None
        except Exception as e:
            print(f"Error inserting vector store: {e}")
            return None

    def modify_vector_store(self, vector_store_id: str, form_data: ModifyVectorStoreForm):
        try:
            with get_db() as db:
                vector_store = db.get(VectorStore, vector_store_id)
                if form_data.name is not None:
                    vector_store.name = form_data.name
                if form_data.metadata is not None:
                    vector_store.meta = form_data.metadata
                if form_data.expires_after is not None:
                    vector_store.expires_after.days = form_data.expires_after.days
                    vector_store.expires_after.anchor = form_data.expires_after.anchor
                db.commit()
                return VectorStoreModel.model_validate(vector_store)
        except Exception as e:
            print(f"Error modifying vector store: {e}")
            return None

    def get_vector_store(self, vector_store_id: str) -> VectorStoreModel | None:
        try:
            with get_db() as db:
                vector_store = db.get(VectorStore, vector_store_id)
                return VectorStoreModel.model_validate(vector_store)
        except Exception as e:
            print(f"Error getting vector store: {e}")
            return None

    def list_vector_stores(self,
                           limit: int | None,
                           order: str | None,
                           after: str | None,
                           before: str | None) -> tuple[list[VectorStoreModel], bool]:
        try:
            with get_db() as db:
                order_by = get_order_expression(order, VectorStore)
                query = db.query(VectorStore).order_by(order_by)
                vector_stores = []
                has_more = False
                for vector_store in query.yield_per(10):
                    if before is not None and vector_store.id == before:
                        break
                    if after is not None:
                        if limit is not None and len(vector_stores) == limit + 1:
                            has_more = True
                            break
                        if vector_store.id == after:
                            vector_stores.append(vector_store)
                        if vector_store.id != after and len(vector_stores) > 0:
                            vector_stores.append(vector_store)
                    elif after is None:
                        if limit is not None and len(vector_stores) == limit:
                            has_more = True
                            break
                        vector_stores.append(vector_store)
                if vector_stores[0].id == after:
                    del vector_stores[0]
                return [VectorStoreModel.model_validate(vector_store) for vector_store in vector_stores], has_more
        except:
            return [], False

    def delete_vector_store_by_id(self, vector_store_id: str):
        with get_db() as db:
            db.query(VectorStore).filter_by(id=vector_store_id).delete()
            db.commit()

    def delete_all_vector_stores(self) -> bool:
        try:
            with get_db() as db:
                db.query(VectorStore).delete()
                return True
        except:
            return False

    def update_usage_bytes(self,
                           vector_store_id: str,
                           usage_bytes: int,
                           ):
        with get_db() as db:
            vector_store = db.get(VectorStore, vector_store_id)
            vector_store.usage_bytes = usage_bytes
            vector_store.last_active_at = int(time.time())
            db.commit()

    def refresh_files_count(self, vector_store_id: str):
        with get_db() as db:
            file_counts = db.get(FileCounts, vector_store_id)
            total_count = db.query(VectorStoreFile.id).count()
            completed_count = db.query(VectorStoreFile.id).filter_by(status="completed").count()
            failed_count = db.query(VectorStoreFile.id).filter_by(status="failed").count()
            in_progress_count = db.query(VectorStoreFile.id).filter_by(status="in_progress").count()
            file_counts.total = total_count
            file_counts.completed = completed_count
            file_counts.failed = failed_count
            file_counts.in_progress = in_progress_count
            db.commit()


VectorStores = VectorStoresTable()


class VectorStoreFilesTable:

    def create_vector_store_file(self,
                                 vector_store_id: str,
                                 form_data: CreateVectorStoreFileForm) -> VectorStoreFileModel | None:
        try:
            chunking_strategy = self.get_chunking_strategy_model(form_data)

            model = VectorStoreFileModel(
                id=str(uuid4()),
                created_at=int(time.time()),
                last_error=None,
                object="vector_store.file",
                status="in_progress",
                usage_bytes=0,
                vector_store_id=vector_store_id,
                chunking_strategy=chunking_strategy,
            )

            result = VectorStoreFile(
                **model.model_dump(exclude={"chunking_strategy"}),
                chunking_strategy=ChunkingStrategy(
                    **model.chunking_strategy.model_dump(exclude={"static"}),
                    static=ChunkingStrategyStatic(**model.chunking_strategy.static.model_dump())),
                file_id=form_data.file_id,
            )
            with get_db() as db:
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return VectorStoreFileModel.model_validate(result, from_attributes=True)
                else:
                    return None

        except Exception as e:
            print(f"Error inserting vector store file: {e}")
            return None

    def get_chunking_strategy_model(self, form_data):
        if form_data.chunking_strategy is not None and form_data.chunking_strategy.type == "static":
            chunking_strategy = ChunkingStrategyStaticModel(
                static=ChunkingStrategyStaticStaticModel(
                    chunk_overlap_tokens=form_data.chunking_strategy.static.chunk_overlap_tokens,
                    max_chunk_size_tokens=form_data.chunking_strategy.static.max_chunk_size_tokens,
                ),
                type="static",
            )
        elif form_data.chunking_strategy is None:
            chunking_strategy = ChunkingStrategyStaticModel(
                static=ChunkingStrategyStaticStaticModel(
                    chunk_overlap_tokens=400,
                    max_chunk_size_tokens=800,
                ),
                type="static")
        else:
            chunking_strategy = ChunkingStrategyOtherModel(
                static=None,
                type="other",
            )
        return chunking_strategy

    def get_vector_store_file(self, vector_store_id: str, file_id: str) -> VectorStoreFileModel | None:
        try:
            with get_db() as db:
                vector_store_file = db.query(VectorStoreFile).filter_by(id=file_id,
                                                                        vector_store_id=vector_store_id).first()
                return VectorStoreFileModel.model_validate(vector_store_file, from_attributes=True)
        except:
            return None

    def delete_vector_store_file(self, vector_store_file_id: str) -> bool:
        try:
            with get_db() as db:
                db.query(VectorStoreFile).filter_by(id=vector_store_file_id).delete()
                db.commit()
                return True
        except:
            return False

    def list_vector_store_files(self,
                                limit: int | None,
                                order: str | None,
                                after: str | None,
                                before: str | None,
                                filter: str | None) -> tuple[list[VectorStoreFileModel], bool]:
        try:
            with get_db() as db:
                filter_by = {}
                if filter is not None:
                    filter_by = {"status": filter}
                order_by = get_order_expression(order, VectorStoreFile)
                query = (db.query(VectorStoreFile)
                         .filter_by(**filter_by)
                         .order_by(order_by))
                vector_store_files = []
                has_more = False
                for vector_store_file in query.yield_per(10):
                    if before is not None and vector_store_file.id == before:
                        break
                    if after is not None:
                        if limit is not None and len(vector_store_files) == limit + 1:
                            has_more = True
                            break
                        if vector_store_file.id == after:
                            vector_store_files.append(vector_store_file)
                        if vector_store_file.id != after and len(vector_store_files) > 0:
                            vector_store_files.append(vector_store_file)
                    elif after is None:
                        if limit is not None and len(vector_store_files) == limit:
                            has_more = True
                            break
                        vector_store_files.append(vector_store_file)
                if vector_store_files[0].id == after:
                    del vector_store_files[0]

                return [VectorStoreFileModel.model_validate(vector_store_file, from_attributes=True)
                        for vector_store_file in vector_store_files], has_more
        except:
            return [], False

    def update_status(self,
                      vector_store_file_id: str,
                      status: str,
                      last_error: LastErrorModel = None
                      ):
        with get_db() as db:
            vector_store_file = db.get(VectorStoreFile, vector_store_file_id)
            vector_store_file.status = status
            if last_error:
                vector_store_file.last_error = LastError(**last_error.model_dump())

            db.commit()

    def update_usage_bytes(self,
                           vector_store_file_id: str,
                           usage_byes: int
                           ):
        with get_db() as db:
            vector_store_file = db.get(VectorStoreFile, vector_store_file_id)
            vector_store_file.usage_bytes = usage_byes
            db.commit()


def get_order_expression(order: str | None, base: Type[VectorStoreFile] | Type[VectorStore]) -> UnaryExpression | None:
    if order == "asc":
        order_by = base.created_at.asc()
    elif order == "desc":
        order_by = base.created_at.desc()
    else:
        order_by = None
    return order_by


VectorStoreFiles = VectorStoreFilesTable()
