from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from . import models, schemas
from .database import get_db

router = APIRouter()


# Patients Routes

@router.get("/patients/", response_model=List[schemas.Patient])
async def read_patients(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Patient).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/patients/", response_model=schemas.Patient)
async def create_patient(item: schemas.PatientCreate, db: AsyncSession = Depends(get_db)):
    db_item = models.Patient(**item.dict(), id=str(uuid.uuid4()))
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/patients/{item_id}", response_model=schemas.Patient)
async def read_patient(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Patient).where(models.Patient.id == item_id))
    item = result.scalars().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return item


# Stays Routes

@router.get("/stays/", response_model=List[schemas.Stay])
async def read_stays(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Stay).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/stays/", response_model=schemas.Stay)
async def create_stay(item: schemas.StayCreate, db: AsyncSession = Depends(get_db)):
    db_item = models.Stay(**item.dict(), id=str(uuid.uuid4()))
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/stays/{item_id}", response_model=schemas.Stay)
async def read_stay(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Stay).where(models.Stay.id == item_id))
    item = result.scalars().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    return item


# Rooms Routes

@router.get("/rooms/", response_model=List[schemas.Room])
async def read_rooms(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Room).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/rooms/", response_model=schemas.Room)
async def create_room(item: schemas.RoomCreate, db: AsyncSession = Depends(get_db)):
    db_item = models.Room(**item.dict(), id=str(uuid.uuid4()))
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/rooms/{item_id}", response_model=schemas.Room)
async def read_room(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Room).where(models.Room.id == item_id))
    item = result.scalars().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return item


