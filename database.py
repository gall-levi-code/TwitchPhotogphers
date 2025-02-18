from sqlalchemy import create_engine, Column, String, Integer, JSON, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# SQLite Database
DATABASE_URL = "sqlite:///twitch_streamers.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Streamer Table
class Streamer(Base):
    __tablename__ = "streamers"

    broadcaster_id = Column(String, primary_key=True, index=True)
    broadcaster_name = Column(String)
    broadcaster_language = Column(String)
    viewers = Column(Integer)
    game_name = Column(String)
    game_id = Column(String)
    title = Column(String)
    tags = Column(JSON)  # Stores list of tags
    stream_url = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Whitelist / Blacklist Table
class UserList(Base):
    __tablename__ = "user_list"

    broadcaster_id = Column(String, primary_key=True, index=True)
    is_whitelisted = Column(Boolean, default=True)  # True = whitelist, False = blacklist

# Create the tables in the database
Base.metadata.create_all(bind=engine)
