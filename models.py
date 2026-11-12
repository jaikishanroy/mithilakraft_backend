from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    mobile_no = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    slug = Column(String(255), unique=True, nullable=False)
    parent_id = Column(Integer, nullable=True)
    status = Column(Boolean, default=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=True)
    sku = Column(String(255), unique=True, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    status = Column(Boolean, default=True, nullable=False)
    cat_image = Column(String(500), nullable=True)
    instagram_link = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    home_blocks = relationship("HomeBlock", back_populates="product", cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    thumbnail = Column(String(500), nullable=True)
    original = Column(String(500), nullable=True)
    large = Column(String(500), nullable=True)
    status = Column(Boolean, default=True, nullable=False)

    product = relationship("Product", back_populates="images")


class HomeBlock(Base):
    __tablename__ = "home_blocks"

    id = Column(Integer, primary_key=True, index=True)
    block = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    product = relationship("Product", back_populates="home_blocks")
    __table_args__ = (UniqueConstraint("block", "product_id", name="uix_home_block_product"),)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(16), nullable=False)
    url = Column(String(500), nullable=True)
    query = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BackgroundTask(Base):
    __tablename__ = "background_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    task_type = Column(String(100), default="csv_import")
    status = Column(String(20), default="queued")
    message = Column(Text, default="")
    error_detail = Column(Text, default="")
    imported_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    file_name = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class FrontSection(Base):
    __tablename__ = "front_sections"

    id = Column(Integer, primary_key=True, index=True)
    block = Column(Integer, nullable=False)
    section = Column(Integer, nullable=False)
    name = Column(String(255), nullable=True)
    image_primary = Column(String(500), nullable=True)
    image_hover = Column(String(500), nullable=True)
    status = Column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("block", "section", name="uix_front_section"),)


class MultiImageSection(Base):
    __tablename__ = "multi_image_sections"

    id = Column(Integer, primary_key=True, index=True)
    block = Column(Integer, nullable=False)
    section = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    status = Column(Boolean, default=True, nullable=False)

    images = relationship("SectionImage", back_populates="section_ref", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("block", "section", name="uix_multi_section"),)


class SectionImage(Base):
    __tablename__ = "section_images"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("multi_image_sections.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    url = Column(String(1000), nullable=True)
    image = Column(String(500), nullable=True)
    order = Column(Integer, default=1, nullable=False)

    section_ref = relationship("MultiImageSection", back_populates="images")


class NewSectionHomeBlock(Base):
    __tablename__ = "new_section_home_blocks"

    id = Column(Integer, primary_key=True, index=True)
    block = Column(Integer, nullable=False)
    section = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    image1 = Column(String(500), nullable=True)
    url1 = Column(String(1000), nullable=True)
    image2 = Column(String(500), nullable=True)
    url2 = Column(String(1000), nullable=True)
    image3 = Column(String(500), nullable=True)
    url3 = Column(String(1000), nullable=True)
    image4 = Column(String(500), nullable=True)
    url4 = Column(String(1000), nullable=True)
    status = Column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("block", "section", name="uix_new_section_home_block"),)
