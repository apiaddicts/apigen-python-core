from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from . import models, schemas
from .database import get_db

router = APIRouter()

{% for resource in resources.resource_list %}
# {{ resource.name }} Routes

@router.get("/{{ resource.slug }}/", response_model=List[schemas.{{ resource.model_name }}])
async def read_{{ resource.slug }}(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.{{ resource.model_name }}).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/{{ resource.slug }}/", response_model=schemas.{{ resource.model_name }})
async def create_{{ resource.model_name.lower() }}(item: schemas.{{ resource.model_name }}Create, db: AsyncSession = Depends(get_db)):
    db_item = models.{{ resource.model_name }}(**item.dict(), id=str(uuid.uuid4()))
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/{{ resource.slug }}/{item_id}", response_model=schemas.{{ resource.model_name }})
async def read_{{ resource.model_name.lower() }}(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.{{ resource.model_name }}).where(models.{{ resource.model_name }}.id == item_id))
    item = result.scalars().first()
    if item is None:
        raise HTTPException(status_code=404, detail="{{ resource.model_name }} not found")
    return item

{% endfor %}
