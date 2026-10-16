"""
database/models/customer.py

customer_id is unique PER ORDER; customer_unique_id identifies the
actual person across multiple orders - use customer_unique_id for
real "distinct customer" counts.
"""
from sqlalchemy import Column, String, Index
from sqlalchemy.orm import relationship
from database.models.base import Base


class Customer(Base):
    __tablename__ = "customers"
    customer_id: str = Column(String(32), primary_key=True)
    customer_unique_id: str = Column(String(32), nullable=False, index=True)
    customer_zip_code_prefix: str = Column(String(10), nullable=True, index=True)
    customer_city: str = Column(String(100), nullable=True)
    customer_state: str = Column(String(2), nullable=True, index=True)

    orders = relationship("Order", back_populates="customer")

    __table_args__ = (
        Index("ix_customers_state_city", "customer_state", "customer_city"),
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.customer_id})>"
