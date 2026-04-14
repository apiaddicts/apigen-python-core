from sqlalchemy import Column, Integer, String, Boolean, DateTime
from .database import Base


class Patient(Base):
    __tablename__ = "patients"

    
    id = Column(String, primary_key=True, index=True)
    
    name = Column(String)
    
    surname = Column(String)
    


class Stay(Base):
    __tablename__ = "stays"

    
    id = Column(String, primary_key=True, index=True)
    
    cause = Column(String)
    
    entry_date = Column(DateTime)
    
    discharge_date = Column(DateTime)
    
    room = Column(String)
    
    patient = Column(String)
    


class Room(Base):
    __tablename__ = "rooms"

    
    id = Column(String, primary_key=True, index=True)
    
    code = Column(String)
    
    active = Column(Boolean)
    


