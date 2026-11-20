"""Ekspor CSV/XLSX dari peta dan halaman partai (T5.4). Wajib login.

Setiap ekspor tercatat di `audit_logs`: siapa, apa, dengan filter apa.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, current_user
from app.core.database import get_session
from app.models import AuditLog, User
from app.models.enums import ElectionType, RegionLevel
from app.services import export, results
from app.services.export import ExportFormat, Table
from app.services.results import NotFoundError

router = APIRouter(tags=["export"])


async def _respond(
    session: AsyncSession,
    request: Request,
    user: User,
    table: Table,
    fmt: ExportFormat,
    filename: str,
    filters: list[tuple[str, str]],
) -> Response:
    body, media_type = export.render(table, fmt, exported_by=user.email, filters=filters)
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="export",
            entity_type="export",
            payload={
                "path": request.url.path,
                "format": fmt,
                "filters": dict(filters),
                "rows": len(table.rows),
            },
            ip_address=client_ip(request),
        )
    )
    await session.commit()
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get(
    "/elections/{election_id}/results/export",
    summary="Unduh hasil satu kontestasi per wilayah (CSV/XLSX)",
)
async def export_election_results(
    election_id: uuid.UUID,
    request: Request,
    level: RegionLevel = RegionLevel.REGENCY,
    parent_id: uuid.UUID | None = None,
    format: ExportFormat = "csv",  # noqa: A002 - nama parameter publik di URL
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        election = await results.get_election(session, election_id)
        data = await results.election_results(session, election, level, parent_id)
    except (NotFoundError, ValueError) as exc:
        raise _http(exc) from exc
    filters = [
        ("Kontestasi", f"{election.election_type.value} {election.election_year}"),
        ("Tingkat wilayah", level.value),
        ("Induk wilayah", str(parent_id) if parent_id else "-"),
    ]
    name = f"hasil_{election.election_type.value}_{election.election_year}_{level.value}"
    return await _respond(
        session, request, user, export.election_results_table(data), format, name, filters
    )


@router.get(
    "/elections/compare/export",
    summary="Unduh swing satu partai antar dua pemilu (CSV/XLSX)",
)
async def export_compare(
    election_type: ElectionType,
    party_id: uuid.UUID,
    request: Request,
    from_year: int = 2019,
    to_year: int = 2024,
    level: RegionLevel = RegionLevel.REGENCY,
    format: ExportFormat = "csv",  # noqa: A002
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        data = await results.compare(session, election_type, from_year, to_year, level, party_id)
    except (NotFoundError, ValueError) as exc:
        raise _http(exc) from exc
    filters = [
        ("Kontestasi", election_type.value),
        ("Partai", data.party.code),
        ("Tahun", f"{from_year} ke {to_year}"),
        ("Tingkat wilayah", level.value),
    ]
    name = f"swing_{data.party.code}_{election_type.value}_{from_year}_{to_year}_{level.value}"
    return await _respond(session, request, user, export.compare_table(data), format, name, filters)


@router.get(
    "/parties/{party_id}/results/export",
    summary="Unduh hasil satu partai lintas tahun (CSV/XLSX)",
)
async def export_party_results(
    party_id: uuid.UUID,
    request: Request,
    election_type: ElectionType = ElectionType.LEGISLATIVE_DPR,
    level: RegionLevel = RegionLevel.REGENCY,
    format: ExportFormat = "csv",  # noqa: A002
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        data = await results.party_results(session, party_id, election_type, level)
    except (NotFoundError, ValueError) as exc:
        raise _http(exc) from exc
    filters = [
        ("Partai", data.party.code),
        ("Kontestasi", election_type.value),
        ("Tingkat wilayah", level.value),
    ]
    name = f"partai_{data.party.code}_{election_type.value}_{level.value}"
    return await _respond(
        session, request, user, export.party_results_table(data), format, name, filters
    )
