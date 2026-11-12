from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    mobile_no: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    mobile_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    slug: str
    parent_id: Optional[int] = None
    status: bool = True


class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    slug: str
    parent_id: Optional[int] = None
    status: bool

    model_config = ConfigDict(from_attributes=True)


class ProductImageOut(BaseModel):
    id: int
    thumbnail: Optional[str] = None
    original: Optional[str] = None
    large: Optional[str] = None
    status: bool

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    name: str
    price: Decimal
    description: Optional[str] = None
    sku: str
    category_id: int
    status: bool = True
    cat_image: Optional[str] = None
    instagram_link: Optional[str] = None


class ProductOut(BaseModel):
    id: int
    name: str
    price: Decimal
    description: Optional[str] = None
    sku: str
    category_id: int
    status: bool
    cat_image: Optional[str] = None
    instagram_link: Optional[str] = None
    category_name: Optional[str] = None
    images: List[ProductImageOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class HomeBlockPayload(BaseModel):
    block: int
    product_ids: List[int]


class HomeBlockOut(BaseModel):
    block: int
    products: List[int]


class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    url: Optional[str] = None
    query: str


class ContactOut(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    url: Optional[str] = None
    query: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackgroundTaskOut(BaseModel):
    id: int
    name: str
    task_type: str
    status: str
    message: str = ""
    error_detail: str = ""
    imported_count: int = 0
    skipped_count: int = 0
    file_name: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FrontSectionCreate(BaseModel):
    block: int
    section: int
    name: Optional[str] = None
    status: bool = True


class SliderImageOut(BaseModel):
    id: int
    title: str
    image: Optional[str] = None
    hover_image: Optional[str] = None
    url: Optional[str] = None
    section: int
    status: bool

    model_config = ConfigDict(from_attributes=True)


class FrontSectionOut(BaseModel):
    id: int
    block: int
    section: int
    name: Optional[str] = None
    image_primary: Optional[str] = None
    image_hover: Optional[str] = None
    status: bool

    model_config = ConfigDict(from_attributes=True)


class SectionImageOut(BaseModel):
    id: int
    title: Optional[str] = None
    url: Optional[str] = None
    image: Optional[str] = None
    order: int

    model_config = ConfigDict(from_attributes=True)


class MultiImageSectionCreate(BaseModel):
    block: int
    section: int
    title: Optional[str] = None
    status: bool = True


class MultiImageSectionOut(BaseModel):
    id: int
    block: int
    section: int
    title: Optional[str] = None
    status: bool
    images: List[SectionImageOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NewSectionHomeBlockCreate(BaseModel):
    block: int
    section: int
    title: Optional[str] = None
    status: bool = True


class NewSectionHomeBlockOut(BaseModel):
    id: int
    block: int
    section: int
    title: Optional[str] = None
    image1: Optional[str] = None
    url1: Optional[str] = None
    image2: Optional[str] = None
    url2: Optional[str] = None
    image3: Optional[str] = None
    url3: Optional[str] = None
    image4: Optional[str] = None
    url4: Optional[str] = None
    status: bool

    model_config = ConfigDict(from_attributes=True)
