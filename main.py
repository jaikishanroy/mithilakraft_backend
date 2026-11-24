import json
import logging
import os
import shutil
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import List
from uuid import uuid4

from PIL import Image, ImageOps

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from models import (
    BackgroundTask,
    Category,
    Contact,
    FrontSection,
    HomeBlock,
    MultiImageSection,
    NewArrivalFeature,
    NewSectionHomeBlock,
    Product,
    ProductImage,
    SectionImage,
    User,
)
from schemas import (
    BackgroundTaskOut,
    CategoryCreate,
    CategoryOut,
    ContactCreate,
    ContactOut,
    FrontSectionCreate,
    FrontSectionOut,
    HomeBlockOut,
    HomeBlockPayload,
    MultiImageSectionCreate,
    MultiImageSectionOut,
    NewArrivalFeatureCreate,
    NewArrivalFeatureOut,
    NewSectionHomeBlockCreate,
    NewSectionHomeBlockOut,
    ProductCreate,
    ProductOut,
    SliderImageOut,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserOut,
)

BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"
MEDIA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

APP_ENV = (os.getenv("APP_ENV") or "local").lower()
APP_BASE_URL = (
    os.getenv("APP_BASE_URL")
    or os.getenv("API_BASE_URL")
    or ("https://api.example.com" if APP_ENV == "production" else "http://localhost:8001")
).rstrip("/")

logger = logging.getLogger("aartikraft")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

app = FastAPI(
    title="Aartikraft FastBackend API",
    version="1.0.0",
    description="FastAPI backend for the Mithila storefront including product catalog, categories, homepage sections, contact management, and authentication.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={"persistAuthorization": True},
)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "aartikraft-admin-secret-key"))
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_request_and_exceptions(request: Request, call_next):
    start_time = time.perf_counter()
    logger.info("Incoming request: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        logger.info(
            "Completed request: %s %s status=%s elapsed=%.3fs",
            request.method,
            request.url.path,
            response.status_code,
            process_time,
        )
        return response
    except Exception:
        process_time = time.perf_counter() - start_time
        logger.exception(
            "Unhandled exception for %s %s after %.3fs",
            request.method,
            request.url.path,
            process_time,
        )
        raise


def resolve_public_base_url(request: Request | None = None) -> str:
    configured_base_url = (
        os.getenv("APP_BASE_URL")
        or os.getenv("API_BASE_URL")
        or ("https://api.example.com" if APP_ENV == "production" else "http://localhost:8001")
    )
    return configured_base_url.rstrip("/") if configured_base_url else (str(request.base_url).rstrip("/") if request else "http://localhost:8001")


def looks_like_url_or_asset(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text.startswith(("http://", "https://", "data:", "mailto:")):
        return True
    if text.startswith(("/", "./", "../", "media/", "static/", "uploads/", "new-arrival/", "cat/", "section/", "front/")):
        return True
    if any(text.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp", ".pdf")):
        return True
    if "/" in text or ("." in text and text.split(".")[-1].isalpha()):
        return True
    return False


def prepend_base_url(value: str | None, base_url: str | None = None) -> str | None:
    if value is None or value == "":
        return value
    if value.startswith(("http://", "https://", "data:")):
        return value
    if not looks_like_url_or_asset(value):
        return value
    normalized_base_url = (base_url or resolve_public_base_url()).rstrip("/")
    if value.startswith("/") and not value.startswith("//"):
        return f"{normalized_base_url}{value}"
    if value.startswith(("./", "../")):
        return f"{normalized_base_url}/{value.lstrip('./')}"
    return f"{normalized_base_url}/{value.lstrip('/')}"


def add_base_url_prefix(value, base_url):
    if isinstance(value, dict):
        return {key: add_base_url_prefix(item, base_url) for key, item in value.items()}
    if isinstance(value, list):
        return [add_base_url_prefix(item, base_url) for item in value]
    if isinstance(value, str):
        if not value or value.startswith(("http://", "https://", "data:")):
            return value
        if looks_like_url_or_asset(value):
            if value.startswith("/") and not value.startswith("//"):
                return f"{base_url}{value}"
            if value.startswith(("./", "../")):
                return f"{base_url}/{value.lstrip('./')}"
            return f"{base_url}/{value.lstrip('/')}"
    return value


@app.middleware("http")
async def add_base_url_to_json_responses(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return response

    base_url = resolve_public_base_url(request)
    headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
    headers["x-base-url"] = base_url

    try:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if not body:
            return response

        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict):
            payload["base_url"] = base_url
        elif isinstance(payload, list):
            payload = {"base_url": base_url, "items": payload}
        else:
            payload = {"base_url": base_url, "data": payload}

        payload = add_base_url_prefix(payload, base_url)

        return Response(
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
            background=response.background,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return response


def ensure_product_schema():
    try:
        with engine.begin() as connection:
            inspector = connection.dialect.get_table_names(connection) if hasattr(connection.dialect, "get_table_names") else None
            if inspector is not None and "products" not in inspector:
                Base.metadata.create_all(bind=engine)
                return

            if "sqlite" in str(engine.url).lower():
                existing = connection.exec_driver_sql("PRAGMA table_info(products)").fetchall()
                existing_cols = {row[1] for row in existing}
            else:
                result = connection.exec_driver_sql(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products'"
                ).fetchall()
                existing_cols = {row[0] for row in result}

            required = {
                "is_new_arrival": "BOOLEAN NOT NULL DEFAULT 0",
                "featured_image": "VARCHAR(500)",
                "material": "VARCHAR(255)",
                "weight": "VARCHAR(255)",
                "chain_length": "VARCHAR(255)",
            }

            for column_name, column_sql in required.items():
                if column_name in existing_cols:
                    continue
                try:
                    if "sqlite" in str(engine.url).lower():
                        connection.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {column_name} {column_sql};")
                    else:
                        connection.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {column_name} {column_sql};")
                except Exception:
                    logger.warning("Could not add column %s to products table; continuing.", column_name)
    except Exception:
        logger.warning("Could not ensure product schema migration; fallback to create_all.", exc_info=True)
        Base.metadata.create_all(bind=engine)


def ensure_new_arrival_schema():
    try:
        with engine.begin() as connection:
            inspector = connection.dialect.get_table_names(connection) if hasattr(connection.dialect, "get_table_names") else None
            if inspector is not None and "new_arrival_features" not in inspector:
                Base.metadata.create_all(bind=engine)
                return

            if "sqlite" in str(engine.url).lower():
                existing = connection.exec_driver_sql("PRAGMA table_info(new_arrival_features)").fetchall()
                existing_cols = {row[1] for row in existing}
            else:
                result = connection.exec_driver_sql(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'new_arrival_features'"
                ).fetchall()
                existing_cols = {row[0] for row in result}

            required = {
                "price": "VARCHAR(100)",
                "material": "VARCHAR(255)",
                "weight": "VARCHAR(255)",
                "chain_length": "VARCHAR(255)",
                "product_url": "VARCHAR(1000)",
                "color_options": "TEXT",
                "size_options": "TEXT",
                "quantity": "INTEGER NOT NULL DEFAULT 1",
            }

            for column_name, column_sql in required.items():
                if column_name in existing_cols:
                    continue
                try:
                    connection.exec_driver_sql(f"ALTER TABLE new_arrival_features ADD COLUMN {column_name} {column_sql};")
                except Exception:
                    logger.warning("Could not add column %s to new_arrival_features table; continuing.", column_name)
    except Exception:
        logger.warning("Could not ensure new_arrival schema migration; fallback to create_all.", exc_info=True)
        Base.metadata.create_all(bind=engine)


Base.metadata.create_all(bind=engine)
ensure_product_schema()
ensure_new_arrival_schema()

try:
    pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")
    pwd_context.hash("compatibility-check")
except Exception:
    logger.warning("bcrypt backend is incompatible in this environment; falling back to pbkdf2_sha256 only.", exc_info=True)
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        if hashed_password and hashed_password.startswith("$2"):
            try:
                import bcrypt as bcrypt_module

                return bcrypt_module.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            except Exception:
                return False
        return False


def get_selected_dashboard_item(db: Session, resource: str, resource_id: str | None):
    if resource_id in (None, ""):
        return None
    try:
        item_id = int(resource_id)
    except (TypeError, ValueError):
        return None

    mapping = {
        "user": User,
        "category": Category,
        "product": Product,
        "contact": Contact,
        "front_section": FrontSection,
        "multi_section": MultiImageSection,
        "new_arrival_feature": NewArrivalFeature,
        "new_section_homeblock": NewSectionHomeBlock,
        "background_task": BackgroundTask,
    }
    model = mapping.get(resource)
    if model is None:
        return None
    return db.query(model).filter(model.id == item_id).first()


def require_admin(request: Request):
    return bool(request.session.get("admin_authenticated"))


def paginate(query, page: int, page_size: int = 10):
    safe_page = max(1, page)
    total = query.count()
    pages = max(1, (total + page_size - 1) // page_size)
    offset = (safe_page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    return items, safe_page, pages, total


def save_upload(file: UploadFile, folder: str) -> str:
    folder_path = MEDIA_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    original_name = os.path.basename(file.filename or "upload")
    file_name, extension = os.path.splitext(original_name)
    safe_name = f"{file_name or 'upload'}-{uuid4().hex}{extension or '.bin'}"
    destination = folder_path / safe_name
    file.file.seek(0)
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    try:
        file.file.seek(0)
        contents = file.file.read()
        file.file.seek(0)
        if extension.lower() in image_exts:
            img = Image.open(BytesIO(contents))
            img = ImageOps.exif_transpose(img)
            if img.mode in {"RGBA", "LA", "P"}:
                img = img.convert("RGB")
            elif img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            limit = 1800
            if img.size[0] > limit or img.size[1] > limit:
                resample = getattr(Image, "Resampling", Image).LANCZOS
                img.thumbnail((limit, limit), resample)
            buffer = BytesIO()
            fmt = "JPEG"
            save_kwargs = {"quality": 85, "optimize": True}
            if extension.lower() == ".png":
                fmt = "PNG"
                save_kwargs = {"optimize": True}
            elif extension.lower() == ".webp":
                fmt = "WEBP"
                save_kwargs = {"quality": 85, "method": 6}
            img.save(buffer, format=fmt, **save_kwargs)
            buffer.seek(0)
            with destination.open("wb") as out_file:
                out_file.write(buffer.getvalue())
            return f"/media/{folder}/{safe_name}"
    except Exception:
        pass

    with destination.open("wb") as buffer:
        file.file.seek(0)
        shutil.copyfileobj(file.file, buffer)
    return f"/media/{folder}/{safe_name}"


def build_product_response(product: Product, db: Session) -> ProductOut:
    category = db.query(Category).filter(Category.id == product.category_id).first()
    images = db.query(ProductImage).filter(ProductImage.product_id == product.id).all()
    base_url = resolve_public_base_url()
    return ProductOut(
        id=product.id,
        name=product.name,
        price=product.price,
        description=product.description,
        sku=product.sku,
        category_id=product.category_id,
        status=bool(product.status),
        is_new_arrival=bool(product.is_new_arrival),
        cat_image=prepend_base_url(product.cat_image, base_url),
        featured_image=prepend_base_url(product.featured_image or product.cat_image, base_url),
        material=product.material,
        weight=product.weight,
        chain_length=product.chain_length,
        instagram_link=product.instagram_link,
        category_name=category.name if category else None,
        images=[
            {
                "id": img.id,
                "thumbnail": prepend_base_url(img.thumbnail, base_url),
                "original": prepend_base_url(img.original, base_url),
                "large": prepend_base_url(img.large, base_url),
                "status": bool(img.status),
            }
            for img in images
        ],
    )


def build_new_arrival_feature_response(feature: NewArrivalFeature) -> NewArrivalFeatureOut:
    base_url = resolve_public_base_url()
    return NewArrivalFeatureOut(
        id=feature.id,
        title=feature.title,
        badge=feature.badge or "New Arrival",
        description=feature.description,
        image=prepend_base_url(feature.image, base_url),
        price=feature.price,
        material=feature.material,
        weight=feature.weight,
        chain_length=feature.chain_length,
        product_url=prepend_base_url(feature.product_url, base_url),
        color_options=feature.color_options,
        size_options=feature.size_options,
        quantity=int(feature.quantity or 1),
        status=bool(feature.status),
        created_at=feature.created_at,
    )


@app.post("/register", response_model=TokenResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password=get_password_hash(payload.password),
        mobile_no=payload.mobile_no,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access="demo-access-token", refresh="demo-refresh-token")


@app.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access="demo-access-token", refresh="demo-refresh-token")


@app.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@app.post("/product", response_model=ProductOut)
def create_product(
    name: str = Form(...),
    price: float = Form(...),
    description: str | None = Form(None),
    sku: str = Form(...),
    category_id: int = Form(...),
    status: bool = Form(True),
    is_new_arrival: bool = Form(False),
    material: str | None = Form(None),
    weight: str | None = Form(None),
    chain_length: str | None = Form(None),
    instagram_link: str | None = Form(None),
    cat_image: UploadFile | None = File(None),
    featured_image: UploadFile | None = File(None),
    images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    cat_image_path = save_upload(cat_image, "cat") if cat_image and getattr(cat_image, "filename", None) else ""
    featured_image_path = save_upload(featured_image, "cat") if featured_image and getattr(featured_image, "filename", None) else None
    product = Product(
        name=name,
        price=price,
        description=description,
        sku=sku,
        category_id=category_id,
        status=status,
        is_new_arrival=is_new_arrival,
        material=material,
        weight=weight,
        chain_length=chain_length,
        instagram_link=instagram_link,
        cat_image=cat_image_path,
        featured_image=featured_image_path or cat_image_path or None,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    for image in images:
        path = save_upload(image, "image")
        db.add(
            ProductImage(
                product_id=product.id,
                thumbnail=path,
                original=path,
                large=path,
                status=True,
            )
        )
    db.commit()
    return build_product_response(product, db)


@app.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return [build_product_response(product, db) for product in products]


@app.get("/new_arrivals", response_model=list[ProductOut])
def list_new_arrivals(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_new_arrival.is_(True)).order_by(Product.id.desc()).all()
    return [build_product_response(product, db) for product in products]


@app.get("/products/new-arrivals", response_model=list[ProductOut])
def list_product_new_arrivals(db: Session = Depends(get_db)):
    return list_new_arrivals(db=db)


@app.get("/new_arrivals/featured", response_model=ProductOut | None)
def get_featured_new_arrival(db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.is_new_arrival.is_(True)).order_by(Product.id.desc()).first()
    if not product:
        return None
    return build_product_response(product, db)


@app.get("/new_arrival_features", response_model=list[NewArrivalFeatureOut])
def list_new_arrival_features(db: Session = Depends(get_db)):
    features = db.query(NewArrivalFeature).order_by(NewArrivalFeature.id.desc()).all()
    return [build_new_arrival_feature_response(feature) for feature in features]


@app.get("/new_arrival_feature", response_model=NewArrivalFeatureOut | None)
def get_new_arrival_feature(db: Session = Depends(get_db)):
    feature = db.query(NewArrivalFeature).filter(NewArrivalFeature.status.is_(True)).order_by(NewArrivalFeature.id.desc()).first()
    if not feature:
        return None
    return build_new_arrival_feature_response(feature)


@app.post("/new_arrival_features/create", response_model=NewArrivalFeatureOut)
def create_new_arrival_feature(
    title: str = Form(...),
    badge: str | None = Form(None),
    description: str | None = Form(None),
    price: str | None = Form(None),
    material: str | None = Form(None),
    weight: str | None = Form(None),
    chain_length: str | None = Form(None),
    product_url: str | None = Form(None),
    color_options: str | None = Form(None),
    size_options: str | None = Form(None),
    quantity: int = Form(1),
    status: bool = Form(True),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    feature = NewArrivalFeature(
        title=title,
        badge=badge or "New Arrival",
        description=description,
        price=price or None,
        material=material or None,
        weight=weight or None,
        chain_length=chain_length or None,
        product_url=product_url or None,
        color_options=color_options or None,
        size_options=size_options or None,
        quantity=max(1, quantity),
        status=status,
        image=save_upload(image, "new-arrival") if image and getattr(image, "filename", None) else None,
    )
    db.add(feature)
    db.commit()
    db.refresh(feature)
    return build_new_arrival_feature_response(feature)


@app.get("/get_product/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return build_product_response(product, db)


@app.get("/block_product")
def block_product(
    category: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    if category:
        query = query.join(Category).filter(Category.slug == category)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if ordering:
        try:
            query = query.order_by(getattr(Product, ordering))
        except AttributeError:
            raise HTTPException(status_code=400, detail="Invalid ordering field")

    products = query.all()
    return [build_product_response(product, db) for product in products]


@app.post("/save_blocks")
def save_blocks(payload: HomeBlockPayload, db: Session = Depends(get_db)):
    db.query(HomeBlock).filter(HomeBlock.block == payload.block).delete()
    for product_id in payload.product_ids:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        db.add(HomeBlock(block=payload.block, product_id=product.id))
    db.commit()
    return {"message": "HomeBlock updated successfully."}


@app.get("/get_product_by_block")
def get_product_by_block(block: str, db: Session = Depends(get_db)):
    block_ids = [int(item.strip()) for item in block.split(",") if item.strip()]
    products = (
        db.query(Product)
        .join(HomeBlock, HomeBlock.product_id == Product.id)
        .filter(HomeBlock.block.in_(block_ids))
        .distinct()
        .all()
    )
    return [build_product_response(product, db) for product in products]


@app.get("/all_blocks")
def get_all_blocks(db: Session = Depends(get_db)):
    blocks = db.query(HomeBlock).all()
    grouped: dict[int, list[int]] = defaultdict(list)
    for block in blocks:
        grouped[block.block].append(block.product_id)
    return [{"block": key, "products": value} for key, value in sorted(grouped.items())]


@app.get("/cat/{name}")
def products_by_category(name: str, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.slug == name).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    products = db.query(Product).filter(Product.category_id == category.id).all()
    return [build_product_response(product, db) for product in products]


@app.get("/all_cat", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()


@app.post("/all_cat", response_model=CategoryOut)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.post("/contact", response_model=ContactOut)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    contact = Contact(**payload.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@app.get("/contact", response_model=list[ContactOut])
def list_contacts(db: Session = Depends(get_db)):
    return db.query(Contact).all()


@app.put("/contact/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, payload: ContactCreate, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in payload.model_dump().items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@app.get("/slider_images", response_model=list[SliderImageOut])
def list_slider_images(block: int = 1, db: Session = Depends(get_db)):
    base_url = resolve_public_base_url()
    slider_images: list[SliderImageOut] = []

    sections = (
        db.query(MultiImageSection)
        .filter(MultiImageSection.block == block, MultiImageSection.status.is_(True))
        .order_by(MultiImageSection.section.asc())
        .all()
    )

    for section in sections:
        for item in sorted(section.images, key=lambda image: image.order):
            image_url = prepend_base_url(item.image, base_url)
            if not image_url:
                continue
            slider_images.append(
                SliderImageOut(
                    id=item.id,
                    title=item.title or section.title or f"Slider {section.section}",
                    image=image_url,
                    hover_image=None,
                    url=prepend_base_url(item.url, base_url) if item.url else None,
                    section=section.section,
                    status=bool(section.status),
                )
            )

    if slider_images:
        return slider_images

    legacy_sections = (
        db.query(FrontSection)
        .filter(FrontSection.block == block, FrontSection.status.is_(True))
        .order_by(FrontSection.section.asc())
        .all()
    )
    for section in legacy_sections:
        image_url = prepend_base_url(section.image_primary or section.image_hover, base_url)
        if not image_url:
            continue
        slider_images.append(
            SliderImageOut(
                id=section.id,
                title=section.name or f"Slider {section.section}",
                image=image_url,
                hover_image=prepend_base_url(section.image_hover, base_url),
                url=None,
                section=section.section,
                status=bool(section.status),
            )
        )
    return slider_images


@app.get("/front_sections", response_model=list[FrontSectionOut])
def list_front_sections(block: int | None = None, db: Session = Depends(get_db)):
    query = db.query(FrontSection)
    if block is not None:
        query = query.filter(FrontSection.block == block)
    sections = query.all()
    base_url = resolve_public_base_url()
    for section in sections:
        section.image_primary = prepend_base_url(section.image_primary, base_url)
        section.image_hover = prepend_base_url(section.image_hover, base_url)
    return sections


@app.post("/front_sections/create", response_model=FrontSectionOut)
def create_front_section(
    block: int = Form(...),
    section: int = Form(...),
    name: str | None = Form(None),
    status: bool = Form(True),
    image_primary: UploadFile | None = File(None),
    image_hover: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    section_obj = db.query(FrontSection).filter(FrontSection.block == block, FrontSection.section == section).first()
    if section_obj is None:
        section_obj = FrontSection(block=block, section=section, name=name, status=status)
        db.add(section_obj)
    else:
        section_obj.name = name
        section_obj.status = status

    if image_primary:
        section_obj.image_primary = save_upload(image_primary, "front/primary")
    if image_hover:
        section_obj.image_hover = save_upload(image_hover, "front/hover")

    db.commit()
    db.refresh(section_obj)
    section_obj.image_primary = prepend_base_url(section_obj.image_primary, resolve_public_base_url())
    section_obj.image_hover = prepend_base_url(section_obj.image_hover, resolve_public_base_url())
    return section_obj


@app.get("/multi_sections", response_model=list[MultiImageSectionOut])
def list_multi_sections(block: int | None = None, db: Session = Depends(get_db)):
    query = db.query(MultiImageSection)
    if block is not None:
        query = query.filter(MultiImageSection.block == block)
    sections = query.all()
    base_url = resolve_public_base_url()
    return [
        MultiImageSectionOut(
            id=section.id,
            block=section.block,
            section=section.section,
            title=section.title,
            status=bool(section.status),
            images=[
                {
                    "id": item.id,
                    "title": item.title,
                    "url": prepend_base_url(item.url, base_url),
                    "image": prepend_base_url(item.image, base_url),
                    "order": item.order,
                }
                for item in section.images
            ],
        )
        for section in sections
    ]


@app.post("/multi_sections/create", response_model=MultiImageSectionOut)
def create_multi_section(
    block: int = Form(...),
    section: int = Form(...),
    title: str | None = Form(None),
    status: bool = Form(True),
    image_1: UploadFile | None = File(None),
    image_2: UploadFile | None = File(None),
    image_3: UploadFile | None = File(None),
    image_4: UploadFile | None = File(None),
    title_1: str | None = Form(None),
    title_2: str | None = Form(None),
    title_3: str | None = Form(None),
    title_4: str | None = Form(None),
    url_1: str | None = Form(None),
    url_2: str | None = Form(None),
    url_3: str | None = Form(None),
    url_4: str | None = Form(None),
    db: Session = Depends(get_db),
):
    section_obj = db.query(MultiImageSection).filter(MultiImageSection.block == block, MultiImageSection.section == section).first()
    if section_obj is None:
        section_obj = MultiImageSection(block=block, section=section, title=title, status=status)
        db.add(section_obj)
        db.commit()
        db.refresh(section_obj)
    else:
        section_obj.title = title
        section_obj.status = status
        db.commit()

    file_map = {
        1: image_1,
        2: image_2,
        3: image_3,
        4: image_4,
    }
    title_map = {1: title_1, 2: title_2, 3: title_3, 4: title_4}
    url_map = {1: url_1, 2: url_2, 3: url_3, 4: url_4}

    for order, image in file_map.items():
        if image or title_map.get(order) or url_map.get(order):
            item = db.query(SectionImage).filter(SectionImage.section_id == section_obj.id, SectionImage.order == order).first()
            if item is None:
                item = SectionImage(section_id=section_obj.id, order=order)
                db.add(item)
            item.title = title_map.get(order)
            item.url = url_map.get(order)
            if image:
                item.image = save_upload(image, "section")
            db.commit()

    db.refresh(section_obj)
    base_url = resolve_public_base_url()
    return MultiImageSectionOut(
        id=section_obj.id,
        block=section_obj.block,
        section=section_obj.section,
        title=section_obj.title,
        status=bool(section_obj.status),
        images=[
            {
                "id": item.id,
                "title": item.title,
                "url": prepend_base_url(item.url, base_url),
                "image": prepend_base_url(item.image, base_url),
                "order": item.order,
            }
            for item in sorted(section_obj.images, key=lambda x: x.order)
        ],
    )


@app.get("/new_section_homeblocks", response_model=list[NewSectionHomeBlockOut])
def list_new_section_homeblocks(block: int | None = None, db: Session = Depends(get_db)):
    query = db.query(NewSectionHomeBlock)
    if block is not None:
        query = query.filter(NewSectionHomeBlock.block == block)
    blocks = query.all()
    base_url = resolve_public_base_url()
    for block in blocks:
        for field in ["image1", "image2", "image3", "image4", "url1", "url2", "url3", "url4"]:
            value = getattr(block, field, None)
            if field.startswith("image"):
                setattr(block, field, prepend_base_url(value, base_url))
            elif field.startswith("url"):
                setattr(block, field, prepend_base_url(value, base_url))
    return blocks


@app.post("/new_section_homeblocks/create", response_model=NewSectionHomeBlockOut)
def create_new_section_homeblock(
    block: int = Form(...),
    section: int = Form(...),
    title: str | None = Form(None),
    status: bool = Form(True),
    image1: UploadFile | None = File(None),
    image2: UploadFile | None = File(None),
    image3: UploadFile | None = File(None),
    image4: UploadFile | None = File(None),
    url1: str | None = Form(None),
    url2: str | None = Form(None),
    url3: str | None = Form(None),
    url4: str | None = Form(None),
    db: Session = Depends(get_db),
):
    block_obj = db.query(NewSectionHomeBlock).filter(NewSectionHomeBlock.block == block, NewSectionHomeBlock.section == section).first()
    if block_obj is None:
        block_obj = NewSectionHomeBlock(block=block, section=section, title=title, status=status)
        db.add(block_obj)
        db.commit()
        db.refresh(block_obj)
    else:
        block_obj.title = title
        block_obj.status = status

    files = {"image1": image1, "image2": image2, "image3": image3, "image4": image4}
    urls = {"url1": url1, "url2": url2, "url3": url3, "url4": url4}

    for key, file_obj in files.items():
        if file_obj:
            setattr(block_obj, key, save_upload(file_obj, "newsection"))
    for key, value in urls.items():
        if value is not None:
            setattr(block_obj, key, value)

    db.commit()
    db.refresh(block_obj)
    base_url = resolve_public_base_url()
    for field in ["image1", "image2", "image3", "image4", "url1", "url2", "url3", "url4"]:
        value = getattr(block_obj, field, None)
        setattr(block_obj, field, prepend_base_url(value, base_url))
    return block_obj


@app.get("/background_tasks", response_model=list[BackgroundTaskOut])
def list_background_tasks(db: Session = Depends(get_db)):
    return db.query(BackgroundTask).order_by(BackgroundTask.created_at.desc()).limit(20).all()


@app.post("/background_tasks", response_model=BackgroundTaskOut)
def create_background_task(
    name: str = Form(...),
    task_type: str = Form("csv_import"),
    status: str = Form("queued"),
    message: str = Form(""),
    error_detail: str = Form(""),
    imported_count: int = Form(0),
    skipped_count: int = Form(0),
    file_name: str = Form(""),
    db: Session = Depends(get_db),
):
    task = BackgroundTask(
        name=name,
        task_type=task_type,
        status=status,
        message=message,
        error_detail=error_detail,
        imported_count=imported_count,
        skipped_count=skipped_count,
        file_name=file_name,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.get("/admin/login")
async def admin_login(request: Request):
    if request.session.get("admin_authenticated"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", {"request": request})


@app.post("/admin/login")
async def admin_login_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if username == admin_user and password == admin_password:
        request.session["admin_authenticated"] = True
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {"request": request, "error": "Invalid username or password"},
    )


@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


RESOURCE_LABELS = {
    "overview": "Overview",
    "users": "Users",
    "categories": "Categories",
    "products": "Products",
    "contacts": "Contacts",
    "front-sections": "Front Sections",
    "multi-sections": "Multi Sections",
    "slider": "Slider",
    "new-arrivals": "New Arrivals",
    "new-home-blocks": "New Home Blocks",
    "background-tasks": "Background Tasks",
}


@app.get("/dashboard")
@app.get("/dashboard/{resource}")
@app.get("/admin")
async def dashboard_view(request: Request, db: Session = Depends(get_db), resource: str | None = None):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    resource = (resource or "").strip().lower() if resource else ""
    if resource and resource not in RESOURCE_LABELS:
        return RedirectResponse(url="/dashboard", status_code=303)
    edit = request.query_params.get("edit")
    edit_id = request.query_params.get("id")
    page_size = 10

    # Each item group gets its own search and pagination data.
    users_query = db.query(User)
    users_search = request.query_params.get("users_search", "")
    if users_search:
        users_query = users_query.filter(User.name.ilike(f"%{users_search}%") | User.email.ilike(f"%{users_search}%"))
    users_page = max(1, int(request.query_params.get("users_page", "1") or 1))
    users, users_page, users_pages, users_total = paginate(users_query.order_by(User.id.desc()), users_page, page_size)

    categories_query = db.query(Category)
    categories_search = request.query_params.get("categories_search", "")
    if categories_search:
        categories_query = categories_query.filter(Category.name.ilike(f"%{categories_search}%") | Category.slug.ilike(f"%{categories_search}%"))
    categories_page = max(1, int(request.query_params.get("categories_page", "1") or 1))
    categories, categories_page, categories_pages, categories_total = paginate(categories_query.order_by(Category.id.desc()), categories_page, page_size)

    products_query = db.query(Product)
    products_search = request.query_params.get("products_search", "")
    if products_search:
        products_query = products_query.filter(Product.name.ilike(f"%{products_search}%") | Product.sku.ilike(f"%{products_search}%"))
    products_page = max(1, int(request.query_params.get("products_page", "1") or 1))
    products, products_page, products_pages, products_total = paginate(products_query.order_by(Product.id.desc()), products_page, page_size)

    contacts_query = db.query(Contact)
    contacts_search = request.query_params.get("contacts_search", "")
    if contacts_search:
        contacts_query = contacts_query.filter(Contact.name.ilike(f"%{contacts_search}%") | Contact.email.ilike(f"%{contacts_search}%"))
    contacts_page = max(1, int(request.query_params.get("contacts_page", "1") or 1))
    contacts, contacts_page, contacts_pages, contacts_total = paginate(contacts_query.order_by(Contact.id.desc()), contacts_page, page_size)

    front_sections_query = db.query(FrontSection)
    front_sections_search = request.query_params.get("front_sections_search", "")
    if front_sections_search:
        front_sections_query = front_sections_query.filter(FrontSection.name.ilike(f"%{front_sections_search}%"))
    front_sections_page = max(1, int(request.query_params.get("front_sections_page", "1") or 1))
    front_sections, front_sections_page, front_sections_pages, front_sections_total = paginate(front_sections_query.order_by(FrontSection.id.desc()), front_sections_page, page_size)

    multi_sections_query = db.query(MultiImageSection)
    multi_sections_search = request.query_params.get("multi_sections_search", "")
    if multi_sections_search:
        multi_sections_query = multi_sections_query.filter(MultiImageSection.title.ilike(f"%{multi_sections_search}%"))
    multi_sections_page = max(1, int(request.query_params.get("multi_sections_page", "1") or 1))
    multi_sections, multi_sections_page, multi_sections_pages, multi_sections_total = paginate(multi_sections_query.order_by(MultiImageSection.id.desc()), multi_sections_page, page_size)

    new_blocks_query = db.query(NewSectionHomeBlock)
    new_blocks_search = request.query_params.get("new_blocks_search", "")
    if new_blocks_search:
        new_blocks_query = new_blocks_query.filter(NewSectionHomeBlock.title.ilike(f"%{new_blocks_search}%"))
    new_blocks_page = max(1, int(request.query_params.get("new_blocks_page", "1") or 1))
    new_section_homeblocks, new_blocks_page, new_blocks_pages, new_blocks_total = paginate(new_blocks_query.order_by(NewSectionHomeBlock.id.desc()), new_blocks_page, page_size)

    new_arrivals_query = db.query(NewArrivalFeature)
    new_arrivals_search = request.query_params.get("new_arrivals_search", "")
    if new_arrivals_search:
        new_arrivals_query = new_arrivals_query.filter(NewArrivalFeature.title.ilike(f"%{new_arrivals_search}%"))
    new_arrivals_page = max(1, int(request.query_params.get("new_arrivals_page", "1") or 1))
    new_arrivals, new_arrivals_page, new_arrivals_pages, new_arrivals_total = paginate(new_arrivals_query.order_by(NewArrivalFeature.id.desc()), new_arrivals_page, page_size)

    background_tasks_query = db.query(BackgroundTask)
    task_search = request.query_params.get("background_tasks_search", "")
    if task_search:
        background_tasks_query = background_tasks_query.filter(BackgroundTask.name.ilike(f"%{task_search}%") | BackgroundTask.task_type.ilike(f"%{task_search}%"))
    background_tasks_page = max(1, int(request.query_params.get("background_tasks_page", "1") or 1))
    background_tasks, background_tasks_page, background_tasks_pages, background_tasks_total = paginate(background_tasks_query.order_by(BackgroundTask.id.desc()), background_tasks_page, page_size)

    selected_items = {
        resource: get_selected_dashboard_item(db, resource, edit_id if edit == resource else None)
        for resource in [
            "user",
            "category",
            "product",
            "contact",
            "front_section",
            "multi_section",
            "new_arrival_feature",
            "new_section_homeblock",
            "background_task",
        ]
    }
    return templates.TemplateResponse(
        request,
        "ninja_dashboard.html",
        {
            "users": users,
            "categories": categories,
            "products": products,
            "contacts": contacts,
            "front_sections": front_sections,
            "multi_sections": multi_sections,
            "new_section_homeblocks": new_section_homeblocks,
            "new_arrivals": new_arrivals,
            "background_tasks": background_tasks,
            "selected_items": selected_items,
            "active_resource": resource,
            "resource_labels": RESOURCE_LABELS,
            "page_meta": {
                "users": {"page": users_page, "pages": users_pages, "total": users_total, "search": users_search},
                "categories": {"page": categories_page, "pages": categories_pages, "total": categories_total, "search": categories_search},
                "products": {"page": products_page, "pages": products_pages, "total": products_total, "search": products_search},
                "contacts": {"page": contacts_page, "pages": contacts_pages, "total": contacts_total, "search": contacts_search},
                "front_sections": {"page": front_sections_page, "pages": front_sections_pages, "total": front_sections_total, "search": front_sections_search},
                "multi_sections": {"page": multi_sections_page, "pages": multi_sections_pages, "total": multi_sections_total, "search": multi_sections_search},
                "new_section_homeblocks": {"page": new_blocks_page, "pages": new_blocks_pages, "total": new_blocks_total, "search": new_blocks_search},
                "new_arrivals": {"page": new_arrivals_page, "pages": new_arrivals_pages, "total": new_arrivals_total, "search": new_arrivals_search},
                "background_tasks": {"page": background_tasks_page, "pages": background_tasks_pages, "total": background_tasks_total, "search": task_search},
            },
        },
    )


@app.post("/admin/save/{resource}")
async def save_admin_resource(resource: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    form = await request.form()
    resource_id = form.get("resource_id") or None
    anchor = {
        "user": "users",
        "category": "categories",
        "product": "products",
        "contact": "contacts",
        "front_section": "front-sections",
        "multi_section": "multi-sections",
        "slider": "slider",
        "new_arrival_feature": "new-arrivals",
        "new_section_homeblock": "new-home-blocks",
        "background_task": "background-tasks",
    }.get(resource, "overview")

    if resource == "user":
        email = (form.get("email") or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        user = db.query(User).filter(User.id == int(resource_id)).first() if resource_id else None
        if user is None:
            user = User(email=email.lower(), name=(form.get("name") or "").strip(), mobile_no=form.get("mobile_no") or None)
            password = (form.get("password") or "").strip()
            if not password:
                raise HTTPException(status_code=400, detail="Password is required to create a user")
            user.password = get_password_hash(password)
            db.add(user)
        else:
            user.email = email.lower()
            user.name = (form.get("name") or "").strip()
            user.mobile_no = form.get("mobile_no") or None
            password = (form.get("password") or "").strip()
            if password:
                user.password = get_password_hash(password)
        db.commit(); db.refresh(user)

    elif resource == "category":
        category = db.query(Category).filter(Category.id == int(resource_id)).first() if resource_id else None
        payload = {
            "name": (form.get("name") or "").strip(),
            "description": form.get("description") or None,
            "slug": (form.get("slug") or "").strip(),
            "parent_id": int(form.get("parent_id")) if (form.get("parent_id") not in (None, "")) else None,
            "status": form.get("status") == "on",
        }
        if not payload["name"] or not payload["slug"]:
            raise HTTPException(status_code=400, detail="Category name and slug are required")
        if category is None:
            category = Category(**payload)
            db.add(category)
        else:
            for key, value in payload.items():
                setattr(category, key, value)
        db.commit(); db.refresh(category)

    elif resource == "product":
        product = db.query(Product).filter(Product.id == int(resource_id)).first() if resource_id else None
        price_value = form.get("price") or 0
        category_id = form.get("category_id")
        if category_id in (None, ""):
            raise HTTPException(status_code=400, detail="Category is required")

        cat_image_field = form.get("cat_image")
        saved_cat_image = product.cat_image if product and product.cat_image else ""
        if cat_image_field and getattr(cat_image_field, "filename", None):
            saved_cat_image = save_upload(cat_image_field, "cat")
        elif isinstance(cat_image_field, str):
            saved_cat_image = (cat_image_field or "").strip() or saved_cat_image

        featured_image_field = form.get("featured_image")
        saved_featured_image = product.featured_image if product and product.featured_image else saved_cat_image
        if featured_image_field and getattr(featured_image_field, "filename", None):
            saved_featured_image = save_upload(featured_image_field, "cat")
        elif isinstance(featured_image_field, str):
            saved_featured_image = (featured_image_field or "").strip() or saved_featured_image

        payload = {
            "name": (form.get("name") or "").strip(),
            "price": float(price_value),
            "description": form.get("description") or None,
            "sku": (form.get("sku") or "").strip(),
            "category_id": int(category_id),
            "status": form.get("status") == "on",
            "is_new_arrival": form.get("is_new_arrival") == "on",
            "material": (form.get("material") or "").strip() or None,
            "weight": (form.get("weight") or "").strip() or None,
            "chain_length": (form.get("chain_length") or "").strip() or None,
            "instagram_link": form.get("instagram_link") or None,
            "cat_image": saved_cat_image,
            "featured_image": saved_featured_image,
        }
        if product is None:
            product = Product(**payload)
            db.add(product); db.commit(); db.refresh(product)
        else:
            for key, value in payload.items():
                setattr(product, key, value)
            db.commit(); db.refresh(product)
        images = [
            form.get(f"image_{i}") for i in range(1, 5)
        ]
        for index, uploaded in enumerate(images, start=1):
            if uploaded and getattr(uploaded, "filename", None):
                path = save_upload(uploaded, "image")
                product_image = db.query(ProductImage).filter(ProductImage.product_id == product.id, ProductImage.id == int(form.get(f"image_id_{index}") or 0)).first() if form.get(f"image_id_{index}") else None
                if product_image is None:
                    product_image = ProductImage(product_id=product.id, thumbnail=path, original=path, large=path, status=True)
                    db.add(product_image)
                else:
                    product_image.thumbnail = path
                    product_image.original = path
                    product_image.large = path
        db.commit()

    elif resource == "contact":
        contact = db.query(Contact).filter(Contact.id == int(resource_id)).first() if resource_id else None
        payload = {
            "name": (form.get("name") or "").strip(),
            "email": (form.get("email") or "").strip(),
            "phone": (form.get("phone") or "").strip(),
            "url": form.get("url") or None,
            "query": (form.get("query") or "").strip(),
        }
        if not payload["name"] or not payload["email"] or not payload["query"]:
            raise HTTPException(status_code=400, detail="Name, email and query are required")
        if contact is None:
            contact = Contact(**payload)
            db.add(contact)
        else:
            for key, value in payload.items():
                setattr(contact, key, value)
        db.commit(); db.refresh(contact)

    elif resource == "front_section":
        block = int(form.get("block") or 0)
        section = int(form.get("section") or 0)
        obj = db.query(FrontSection).filter(FrontSection.id == int(resource_id)).first() if resource_id else None
        if obj is None:
            obj = db.query(FrontSection).filter(FrontSection.block == block, FrontSection.section == section).first()
        if obj is None:
            obj = FrontSection(block=block, section=section)
            db.add(obj)
        obj.name = (form.get("name") or "").strip() or None
        obj.status = form.get("status") == "on"
        primary = form.get("image_primary")
        hover = form.get("image_hover")
        if primary and getattr(primary, "filename", None):
            obj.image_primary = save_upload(primary, "front/primary")
        if hover and getattr(hover, "filename", None):
            obj.image_hover = save_upload(hover, "front/hover")
        db.commit(); db.refresh(obj)

    elif resource == "multi_section":
        block = int(form.get("block") or 0)
        section = int(form.get("section") or 0)
        obj = db.query(MultiImageSection).filter(MultiImageSection.id == int(resource_id)).first() if resource_id else None
        if obj is None:
            obj = db.query(MultiImageSection).filter(MultiImageSection.block == block, MultiImageSection.section == section).first()
        if obj is None:
            obj = MultiImageSection(block=block, section=section)
            db.add(obj)
            db.commit(); db.refresh(obj)
        obj.title = (form.get("title") or "").strip() or None
        obj.status = form.get("status") == "on"
        for idx in range(1, 5):
            image = form.get(f"image_{idx}")
            title_value = (form.get(f"title_{idx}") or "").strip() or None
            url_value = form.get(f"url_{idx}") or None
            if image and getattr(image, "filename", None):
                saved_path = save_upload(image, "section")
            else:
                saved_path = None
            item = db.query(SectionImage).filter(SectionImage.section_id == obj.id, SectionImage.order == idx).first()
            if item is None and (title_value or url_value or saved_path):
                item = SectionImage(section_id=obj.id, order=idx)
                db.add(item)
            if item is not None:
                item.title = title_value
                item.url = url_value
                if saved_path:
                    item.image = saved_path
        db.commit(); db.refresh(obj)

    elif resource == "slider":
        block = int(form.get("block") or 1)
        section = int(form.get("section") or 1)
        obj = db.query(MultiImageSection).filter(MultiImageSection.id == int(resource_id)).first() if resource_id else None
        if obj is None:
            obj = db.query(MultiImageSection).filter(MultiImageSection.block == block, MultiImageSection.section == section).first()
        if obj is None:
            obj = MultiImageSection(block=block, section=section)
            db.add(obj)
            db.commit(); db.refresh(obj)
        obj.title = (form.get("title") or "").strip() or None
        obj.status = form.get("status") == "on"
        slider_files = form.getlist("slider_images")
        slider_titles = form.getlist("slider_titles")
        slider_links = form.getlist("slider_links")
        total = max(len(slider_files), len(slider_titles), len(slider_links))
        for idx in range(total):
            image = slider_files[idx] if idx < len(slider_files) else None
            title_value = (slider_titles[idx] if idx < len(slider_titles) else "").strip() or None
            url_value = slider_links[idx] if idx < len(slider_links) else None
            saved_path = save_upload(image, "section") if image and getattr(image, "filename", None) else None
            item = db.query(SectionImage).filter(SectionImage.section_id == obj.id, SectionImage.order == idx + 1).first()
            if item is None and (title_value or url_value or saved_path):
                item = SectionImage(section_id=obj.id, order=idx + 1)
                db.add(item)
            if item is not None:
                item.title = title_value
                item.url = url_value
                if saved_path:
                    item.image = saved_path
        db.commit(); db.refresh(obj)

    elif resource == "new_arrival_feature":
        obj = db.query(NewArrivalFeature).filter(NewArrivalFeature.id == int(resource_id)).first() if resource_id else None
        if obj is None:
            obj = NewArrivalFeature(title=(form.get("title") or "").strip() or "New Arrival")
            db.add(obj)
        obj.title = (form.get("title") or "").strip() or obj.title
        obj.badge = (form.get("badge") or "").strip() or "New Arrival"
        obj.description = form.get("description") or None
        obj.price = (form.get("price") or "").strip() or None
        obj.material = (form.get("material") or "").strip() or None
        obj.weight = (form.get("weight") or "").strip() or None
        obj.chain_length = (form.get("chain_length") or "").strip() or None
        obj.product_url = (form.get("product_url") or "").strip() or None
        obj.color_options = (form.get("color_options") or "").strip() or None
        obj.size_options = (form.get("size_options") or "").strip() or None
        quantity_value = form.get("quantity")
        try:
            obj.quantity = max(1, int(quantity_value or 1))
        except (TypeError, ValueError):
            obj.quantity = 1
        obj.status = form.get("status") == "on"
        image = form.get("image")
        if image and getattr(image, "filename", None):
            obj.image = save_upload(image, "new-arrival")
        db.commit(); db.refresh(obj)

    elif resource == "new_section_homeblock":
        block = int(form.get("block") or 0)
        section = int(form.get("section") or 0)
        obj = db.query(NewSectionHomeBlock).filter(NewSectionHomeBlock.id == int(resource_id)).first() if resource_id else None
        if obj is None:
            obj = db.query(NewSectionHomeBlock).filter(NewSectionHomeBlock.block == block, NewSectionHomeBlock.section == section).first()
        if obj is None:
            obj = NewSectionHomeBlock(block=block, section=section)
            db.add(obj)
        obj.title = (form.get("title") or "").strip() or None
        obj.status = form.get("status") == "on"
        for idx in range(1, 5):
            image = form.get(f"image{idx}")
            url_key = f"url{idx}"
            if image and getattr(image, "filename", None):
                setattr(obj, f"image{idx}", save_upload(image, "newsection"))
            value = form.get(url_key)
            if value is not None:
                setattr(obj, url_key, value)
        db.commit(); db.refresh(obj)

    elif resource == "background_task":
        task = db.query(BackgroundTask).filter(BackgroundTask.id == int(resource_id)).first() if resource_id else None
        payload = {
            "name": (form.get("name") or "").strip(),
            "task_type": (form.get("task_type") or "csv_import").strip() or "csv_import",
            "status": (form.get("status") or "queued").strip() or "queued",
            "message": form.get("message") or "",
            "error_detail": form.get("error_detail") or "",
            "imported_count": int(form.get("imported_count") or 0),
            "skipped_count": int(form.get("skipped_count") or 0),
            "file_name": form.get("file_name") or "",
        }
        if task is None:
            task = BackgroundTask(**payload)
            db.add(task)
        else:
            for key, value in payload.items():
                setattr(task, key, value)
        db.commit(); db.refresh(task)

    return RedirectResponse(url=f"/dashboard#{anchor}", status_code=303)


@app.post("/admin/delete/{resource}/{resource_id}")
async def delete_admin_resource(resource: str, resource_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    mapping = {
        "user": User,
        "category": Category,
        "product": Product,
        "contact": Contact,
        "front_section": FrontSection,
        "multi_section": MultiImageSection,
        "new_arrival_feature": NewArrivalFeature,
        "new_section_homeblock": NewSectionHomeBlock,
        "background_task": BackgroundTask,
    }
    model = mapping.get(resource)
    if model is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    item = db.query(model).filter(model.id == resource_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    anchor = {
        "user": "users",
        "category": "categories",
        "product": "products",
        "contact": "contacts",
        "front_section": "front-sections",
        "multi_section": "multi-sections",
        "new_arrival_feature": "new-arrivals",
        "new_section_homeblock": "new-home-blocks",
        "background_task": "background-tasks",
    }.get(resource, "overview")
    return RedirectResponse(url=f"/dashboard#{anchor}", status_code=303)


@app.get("/")
def read_root():
    return {
        "title": "Aartikraft FastBackend API",
        "description": "FastAPI replica of the Mithila storefront backend.",
        "features": [
            "authentication",
            "product management",
            "category management",
            "homepage blocks",
            "contact management",
            "front sections",
            "multi-image sections",
            "new section home blocks",
            "background task tracking",
            "admin dashboard",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
