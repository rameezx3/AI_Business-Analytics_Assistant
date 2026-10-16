"""database/models/order_payment.py - composite PK (order_id, payment_sequential)."""
from sqlalchemy import Column, String, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from database.models.base import Base


class OrderPayment(Base):
    __tablename__ = "order_payments"
    order_id: str = Column(String(32), ForeignKey("orders.order_id"), primary_key=True)
    payment_sequential: int = Column(Integer, primary_key=True)
    payment_type: str = Column(String(20), nullable=False, index=True)
    payment_installments: int = Column(Integer, nullable=True)
    payment_value: float = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="payments")

    def __repr__(self) -> str:
        return f"<OrderPayment(order={self.order_id})>"
