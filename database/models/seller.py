"""database/models/seller.py"""
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from database.models.base import Base


class Seller(Base):
    __tablename__ = "sellers"
    seller_id: str = Column(String(32), primary_key=True)
    seller_zip_code_prefix: str = Column(String(10), nullable=True, index=True)
    seller_city: str = Column(String(100), nullable=True)
    seller_state: str = Column(String(2), nullable=True, index=True)

    order_items = relationship("OrderItem", back_populates="seller")

    def __repr__(self) -> str:
        return f"<Seller(id={self.seller_id})>"
