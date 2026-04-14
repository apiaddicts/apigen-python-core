from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PatientBase(BaseModel):
    
    
    
    
    name: str
    
    
    
    surname: str
    
    

class PatientCreate(PatientBase):
    pass

class Patient(PatientBase):
    id: str

    class Config:
        orm_mode = True


class StayBase(BaseModel):
    
    
    
    
    cause: str
    
    
    
    entry_date: datetime
    
    
    
    discharge_date: Optional[datetime] = None
    
    
    
    room: str
    
    
    
    patient: str
    
    

class StayCreate(StayBase):
    pass

class Stay(StayBase):
    id: str

    class Config:
        orm_mode = True


class RoomBase(BaseModel):
    
    
    
    
    code: str
    
    
    
    active: bool
    
    

class RoomCreate(RoomBase):
    pass

class Room(RoomBase):
    id: str

    class Config:
        orm_mode = True


