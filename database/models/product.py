"""
database/models/product.py

product_category_name is a real FK into category_translation - verified
against the dataset: every non-null category has a matching translation.
"""
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database.models.base import Base


class Product(Base):
    __tablename__ = "products"
    product_id: str = Column(String(32), primary_key=True)
    product_category_name: str = Column(
        String(100), ForeignKey("category_translation.product_category_name"),
        nullable=True, index=True,
    )
    product_name_lenght: int = Column(Integer, nullable=True)
    product_description_lenght: int = Column(Integer, nullable=True)
    product_photos_qty: int = Column(Integer, nullable=True)
    product_weight_g: int = Column(Integer, nullable=True)
    product_length_cm: int = Column(Integer, nullable=True)
    product_height_cm: int = Column(Integer, nullable=True)
    product_width_cm: int = Column(Integer, nullable=True)

    category = relationship("CategoryTranslation")
    order_items = relationship("OrderItem", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product(id={self.product_id})>"
