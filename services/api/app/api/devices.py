"""Devices endpoints — register, list, revoke trusted devices."""

import secrets
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import Device, User

router = APIRouter()


class DeviceResponse(BaseModel):
    id: str
    device_name: str
    platform: str
    is_active: bool
    registered_at: datetime


class RegisterDeviceRequest(BaseModel):
    device_name: str
    platform: str = "android"


class RegisterDeviceResponse(BaseModel):
    id: str
    device_token: str   # returned ONCE — store in Android Keystore
    device_name: str
    platform: str


@router.get("", response_model=List[DeviceResponse])
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    return [
        DeviceResponse(
            id=d.id, device_name=d.device_name,
            platform=d.platform, is_active=d.is_active,
            registered_at=d.registered_at,
        )
        for d in result.scalars().all()
    ]


@router.post("/register", response_model=RegisterDeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: RegisterDeviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = secrets.token_urlsafe(32)
    device = Device(
        user_id=current_user.id,
        device_name=body.device_name,
        device_token=token,
        platform=body.platform,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return RegisterDeviceResponse(
        id=device.id,
        device_token=token,
        device_name=device.device_name,
        platform=device.platform,
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.user_id == current_user.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.is_active = False
    await db.commit()
