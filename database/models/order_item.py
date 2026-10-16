"""database/models/order_item.py - composite PK (order_id, order_item_id)."""
from sqlalchemy import Column, String, Integer, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from database.models.base import Base


class OrderItem(Base):
    __tablename__ = "order_items"
    order_id: str = Column(String(32), ForeignKey("orders.order_id"), primary_key=True)
    order_item_id: int = Column(Integer, primary_key=True)
    product_id: str = Column(String(32), ForeignKey("products.product_id"), nullable=False, index=True)
    seller_id: str = Column(String(32), ForeignKey("sellers.seller_id"), nullable=False, index=True)
    shipping_limit_date = Column(DateTime, nullable=True)
    price: float = Column(Numeric(10, 2), nullable=False)
    freight_value: float = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    seller = relationship("Seller", back_populates="order_items")

    def __repr__(self) -> str:
        return f"<OrderItem(order={self.order_id}, item={self.order_item_id})>"
