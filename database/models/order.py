"""database/models/order.py - the central fact table."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from database.models.base import Base


class Order(Base):
    __tablename__ = "orders"
    order_id: str = Column(String(32), primary_key=True)
    customer_id: str = Column(String(32), ForeignKey("customers.customer_id"), nullable=False, index=True)
    order_status: str = Column(String(20), nullable=False, index=True)
    order_purchase_timestamp = Column(DateTime, nullable=True, index=True)
    order_approved_at = Column(DateTime, nullable=True)
    order_delivered_carrier_date = Column(DateTime, nullable=True)
    order_delivered_customer_date = Column(DateTime, nullable=True)
    order_estimated_delivery_date = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("OrderPayment", back_populates="order", cascade="all, delete-orphan")
    reviews = relationship("OrderReview", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_orders_status_purchase", "order_status", "order_purchase_timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.order_id})>"
