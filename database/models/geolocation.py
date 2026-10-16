"""database/models/geolocation.py - zip prefix -> lat/lng lookup, no FKs."""
from sqlalchemy import Column, Integer, String, Float, Index
from database.models.base import Base


class Geolocation(Base):
    __tablename__ = "geolocation"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    geolocation_zip_code_prefix: str = Column(String(10), nullable=False, index=True)
    geolocation_lat: float = Column(Float, nullable=True)
    geolocation_lng: float = Column(Float, nullable=True)
    geolocation_city: str = Column(String(100), nullable=True)
    geolocation_state: str = Column(String(2), nullable=True, index=True)

    __table_args__ = (
        Index("ix_geo_zip_state", "geolocation_zip_code_prefix", "geolocation_state"),
    )

    def __repr__(self) -> str:
        return f"<Geolocation(zip={self.geolocation_zip_code_prefix})>"
