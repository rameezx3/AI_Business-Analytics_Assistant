"""
database/models/order_review.py

Surrogate integer PK: review_id is NOT globally unique (789 review_id
values are reused across different orders, verified against the
dataset). The natural key is (review_id, order_id), enforced here.
"""
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from database.models.base import Base


class OrderReview(Base):
    __tablename__ = "order_reviews"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    review_id: str = Column(String(32), nullable=False, index=True)
    order_id: str = Column(String(32), ForeignKey("orders.order_id"), nullable=False, index=True)
    review_score: int = Column(Integer, nullable=False)
    review_comment_title: str = Column(String(255), nullable=True)
    review_comment_message: str = Column(String(2000), nullable=True)
    review_creation_date = Column(DateTime, nullable=True)
    review_answer_timestamp = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("review_id", "order_id", name="uq_review_order"),
    )

    def __repr__(self) -> str:
        return f"<OrderReview(review={self.review_id}, order={self.order_id})>"
