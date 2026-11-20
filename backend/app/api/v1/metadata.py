"""Metadata sumber dan riwayat versi dataset (T5.3). Hanya membaca; wajib login."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.metadata import DatasetHistory, DatasetSummary, SourceDetail, SourceOut
from app.services import metadata
from app.services.results import NotFoundError

router = APIRouter(tags=["metadata"])


@router.get("/sources", response_model=list[SourceOut], summary="Daftar dokumen sumber")
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[SourceOut]:
    return await metadata.list_sources(session)


@router.get(
    "/sources/{source_id}",
    response_model=SourceDetail,
    summary="Satu sumber beserta versi dataset yang berasal darinya",
)
async def source_detail(
    source_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SourceDetail:
    try:
        return await metadata.source_detail(session, source_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get(
    "/datasets",
    response_model=list[DatasetSummary],
    summary="Ringkasan setiap dataset dan versi yang sedang dipakai",
)
async def list_datasets(session: AsyncSession = Depends(get_session)) -> list[DatasetSummary]:
    return await metadata.list_datasets(session)


@router.get(
    "/datasets/{dataset_name}",
    response_model=DatasetHistory,
    summary="Riwayat semua versi satu dataset",
)
async def dataset_history(
    dataset_name: str, session: AsyncSession = Depends(get_session)
) -> DatasetHistory:
    try:
        return await metadata.dataset_history(session, dataset_name)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
