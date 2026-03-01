from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import challenge_service

router = APIRouter(prefix="/api/challenges", tags=["challenges"])


class ChallengeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    target_amount: int = 0
    deadline: str
    milestones: Optional[list] = None


class ChallengeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_amount: Optional[int] = None
    deadline: Optional[str] = None
    status: Optional[str] = None
    milestones: Optional[list] = None


class EarningCreate(BaseModel):
    amount: int
    source: Optional[str] = None
    date: Optional[str] = None
    note: Optional[str] = None


class MilestoneUpdate(BaseModel):
    status: str  # 'pending' | 'completed'


@router.get("")
async def list_challenges(status: Optional[str] = Query(None)):
    return await challenge_service.list_challenges(status)


@router.get("/{challenge_id}")
async def get_challenge(challenge_id: int):
    result = await challenge_service.get_challenge(challenge_id)
    if not result:
        raise HTTPException(404, "Challenge not found")
    return result


@router.post("")
async def create_challenge(body: ChallengeCreate):
    return await challenge_service.create_challenge(body.model_dump())


@router.put("/{challenge_id}")
async def update_challenge(challenge_id: int, body: ChallengeUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await challenge_service.update_challenge(challenge_id, data)
    if not result:
        raise HTTPException(404, "Challenge not found")
    return result


@router.post("/{challenge_id}/earning")
async def add_earning(challenge_id: int, body: EarningCreate):
    result = await challenge_service.add_earning(challenge_id, body.model_dump())
    if not result:
        raise HTTPException(404, "Challenge not found")
    return result


@router.get("/{challenge_id}/progress")
async def get_progress(challenge_id: int):
    result = await challenge_service.get_progress(challenge_id)
    if not result:
        raise HTTPException(404, "Challenge not found")
    return result


@router.put("/{challenge_id}/milestone/{milestone_index}")
async def update_milestone(challenge_id: int, milestone_index: int, body: MilestoneUpdate):
    result = await challenge_service.update_milestone(
        challenge_id, milestone_index, body.status
    )
    if not result:
        raise HTTPException(404, "Challenge or milestone not found")
    return result
