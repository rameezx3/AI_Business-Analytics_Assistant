"""
database/models package - registers every model on shared Base.metadata.
Importing this guarantees all tables are known before create_all().
"""
from database.models.base import Base
from database.models.category_translation import CategoryTranslation
from database.models.customer import Customer
from database.models.geolocation import Geolocation
from database.models.seller import Seller
from database.models.product import Product
from database.models.order import Order
from database.models.order_item import OrderItem
from database.models.order_payment import OrderPayment
from database.models.order_review import OrderReview
from database.models.data_quality_log import DataQualityLog
from database.models.validation_log import ValidationLog
from database.models.app_user import AppUser

# Dependency order for CSV import: parents before children.
# NOTE: DataQualityLog and ValidationLog are deliberately excluded -
# neither has a source CSV (Module 4/5 populate them, not Module 3's
# importer), but both ARE registered on Base, so
# Base.metadata.create_all() still creates them.
MODEL_LOAD_ORDER = [
    CategoryTranslation, Customer, Geolocation, Seller, Product,
    Order, OrderItem, OrderPayment, OrderReview,
]

__all__ = [
    "Base", "CategoryTranslation", "Customer", "Geolocation", "Seller",
    "Product", "Order", "OrderItem", "OrderPayment", "OrderReview",
    "DataQualityLog", "ValidationLog", "MODEL_LOAD_ORDER",
    "AppUser",
]
