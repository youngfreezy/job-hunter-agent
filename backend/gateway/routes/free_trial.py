# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Compatibility responses for the retired anonymous trial flow.

Free credits remain available after verified sign-in through /api/sessions.
A resume email cannot prove account ownership or authorize a paid workflow.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.shared.models.schemas import StartSessionRequest

router = APIRouter(prefix="/api/free-trial", tags=["free-trial"])


def _signin_required():
    raise HTTPException(status_code=401, detail="Sign in to start your free trial. Your free application credits are available after sign-in.")


@router.post("/parse-resume")
async def free_trial_parse_resume(request: Request):
    _signin_required()


@router.post("/start")
async def free_trial_start(body: StartSessionRequest, request: Request):
    _signin_required()


class ConvertRequest(BaseModel):
    trial_token: str
    password: str
    name: Optional[str] = None


@router.post("/convert")
async def free_trial_convert(body: ConvertRequest, request: Request):
    _signin_required()
