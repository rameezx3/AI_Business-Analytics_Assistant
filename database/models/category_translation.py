"""database/models/category_translation.py - PT->EN category lookup table."""
from sqlalchemy import Column, String
from database.models.base import Base


class CategoryTranslation(Base):
    __tablename__ = "category_translation"
    product_category_name: str = Column(String(100), primary_key=True)
    product_category_name_english: str = Column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<CategoryTranslation({self.product_category_name})>"
