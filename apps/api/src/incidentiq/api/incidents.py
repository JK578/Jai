from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from incidentiq.application.incidents import IncidentNotFound, IncidentService
from incidentiq.domain.incidents import (
    DESCRIPTION_MAX,
    SERVICE_MAX,
    TITLE_MAX,
    IncidentStatus,
    Severity,
)


class CreateIncidentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    severity: Severity = Severity.MEDIUM
    service_name: str = Field(min_length=1, max_length=SERVICE_MAX)


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    severity: Severity
    status: IncidentStatus
    service_name: str
    created_at: datetime
    updated_at: datetime


def incident_router(service: IncidentService) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/incidents",
        tags=["incidents"],
        responses={503: {"description": "Incident storage unavailable"}},
    )

    @router.post(
        "",
        response_model=IncidentResponse,
        status_code=201,
        responses={409: {"description": "Incident identity conflict"}},
    )
    def create_incident(payload: CreateIncidentRequest, response: Response) -> IncidentResponse:
        incident = service.create(
            payload.title,
            payload.description,
            payload.severity,
            payload.service_name,
        )
        response.headers["Location"] = f"/api/v1/incidents/{incident.id}"
        response.headers["Cache-Control"] = "no-store"
        return IncidentResponse.model_validate(incident)

    @router.get("", response_model=list[IncidentResponse])
    def list_incidents(response: Response) -> list[IncidentResponse]:
        response.headers["Cache-Control"] = "no-store"
        return [IncidentResponse.model_validate(item) for item in service.list()]

    @router.get(
        "/{incident_id}",
        response_model=IncidentResponse,
        responses={404: {"description": "Incident not found"}},
    )
    def get_incident(incident_id: UUID, response: Response) -> IncidentResponse:
        response.headers["Cache-Control"] = "no-store"
        try:
            return IncidentResponse.model_validate(service.get(incident_id))
        except IncidentNotFound as error:
            raise HTTPException(status_code=404, detail="Incident not found") from error

    return router
