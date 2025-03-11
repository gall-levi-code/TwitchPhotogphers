import logging
from sqlalchemy import create_engine, Column, String, Integer, JSON, DateTime, PrimaryKeyConstraint
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timezone

# ✅ Configure logging
# logging.basicConfig(
#     filename="database.log",
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

logging.basicConfig(level=logging.INFO)

DATABASE_URL = "sqlite:///twitch_streamers.db"
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=30, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DatabaseManager:
    """Global Database Manager to handle all DB interactions with logging."""

    def __init__(self):
        self.Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def get_session(self):
        """Creates and returns a new database session."""
        logging.info("🔄 Creating new database session")
        return self.Session()

    def close_session(self, session):
        """Commits and closes the session safely."""
        try:
            session.commit()
            logging.info("✅ Database session committed successfully")
        except Exception as e:
            session.rollback()
            logging.error(f"⚠️ Database commit failed: {e}")
        finally:
            session.close()
            logging.info("🔒 Database session closed")

    def add_entry(self, entry):
        """Adds a new entry to the database."""
        session = self.get_session()
        try:
            session.add(entry)
            self.close_session(session)
            logging.info(f"📝 Added entry: {entry}")
        except Exception as e:
            logging.error(f"⚠️ Error adding entry: {e}")
            session.rollback()
            session.close()

    def get_one(self, model, **filters):
        """Retrieves one record from a given model."""
        session = self.get_session()
        try:
            result = session.query(model).filter_by(**filters).first()
            logging.info(f"🔍 Fetched one from {model.__name__} with filters {filters}: {result}")
            return result
        finally:
            session.close()

    def get_all(self, model, **filters):
        """Retrieves all records matching the filters."""
        session = self.get_session()
        try:
            results = session.query(model).filter_by(**filters).all()
            logging.info(f"📋 Fetched all from {model.__name__} with filters {filters}: {len(results)} records")
            return results
        finally:
            session.close()

    def delete_entry(self, model, **filters):
        """Deletes an entry from the database."""
        session = self.get_session()
        try:
            entry = session.query(model).filter_by(**filters).first()
            if entry:
                session.delete(entry)
                self.close_session(session)
                logging.info(f"🗑️ Deleted entry from {model.__name__} with filters {filters}")
                return True
            logging.warning(f"⚠️ No matching entry found for deletion in {model.__name__} with filters {filters}")
            return False
        except Exception as e:
            logging.error(f"⚠️ Error deleting entry: {e}")
            session.rollback()
            session.close()
            return False

# ✅ Initialize Global Database Manager
db_manager = DatabaseManager()

# ✅ Define Tables
class ServerSettings(Base):
    __tablename__ = "server_settings"

    guild_id = Column(String, primary_key=True, index=True)
    approval_channel_id = Column(String, nullable=True)
    broadcast_channel_id = Column(String, nullable=True)

class Streamer(Base):
    __tablename__ = "streamers"

    guild_id = Column(String)
    broadcaster_id = Column(String)
    message_id = Column(String, default="")
    broadcaster_name = Column(String)
    broadcaster_language = Column(String)
    viewers = Column(Integer)
    game_name = Column(String)
    game_id = Column(String)
    title = Column(String)
    tags = Column(JSON)
    stream_url = Column(String)
    status = Column(String, default="pending")
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    __table_args__ = (PrimaryKeyConstraint("guild_id", "broadcaster_id"),)

class SearchTags(Base):
    __tablename__ = "search_tags"

    guild_id = Column(String, primary_key=True, index=True)
    search_tags = Column(JSON)
    search_interval = Column(Integer)

Base.metadata.create_all(bind=engine)
logging.info("✅ Database initialized and tables created")

