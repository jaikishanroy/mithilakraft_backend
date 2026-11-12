# Aartikarft FastBackend API

This backend API is built with Django and Django REST Framework for a product catalog and storefront application. It handles product management, category browsing, user authentication, homepage blocks, contact submissions, and image-based marketing sections used by the frontend.

## Core Features

### 1. User Authentication and Authorization
- User registration with email-based signup
- Secure password hashing using Django's built-in auth system
- JWT-based login using `rest_framework_simplejwt`
- Access token and refresh token generation
- Cookie-based JWT storage (`jwt` cookie) after login

### 2. Product Catalog Management
- Add new products with name, SKU, price, description, category, status, and image
- Fetch all products
- Fetch single product by ID
- Filter products by category
- Search by product name
- Pagination and ordering support for product lists
- Product images with thumbnail, original, and large variants

### 3. Category Management
- Create and list categories
- Category-based product grouping
- Product retrieval by category slug
- Category metadata: name, description, slug, status, parent ID

### 4. Homepage Product Blocks
- Save product groups to homepage blocks
- Store product IDs under a block number
- Retrieve products assigned to a specific block
- Group all products by block for homepage layouts
- Use `HomeBlock` model to manage homepage product placement

### 5. Contact and Inquiry Management
- Submit contact form entries
- Store customer name, email, phone, URL, and message/query
- List all contact submissions
- Update individual contact records

### 6. Front-End Promotional Sections
- Manage `FrontSection` objects for homepage feature blocks
- Each block supports up to 4 sections
- Each section contains primary and hover images
- Image resizing support for consistent frontend display
- Optional status flag for visibility control

### 7. Multi-Image Section Management
- Create dynamic multi-image content sections
- Each section can contain up to 4 image items
- Store item title, URL, order, and image file
- Retrieve section data with image URLs
- Support block-level filtering

### 8. New Section Home Blocks
- Manage compact homepage blocks with 4 image slots
- Each slot stores an image and URL
- Supports block and section-based organization
- Status control for enabling/disabling the section

### 9. Background Task Tracking
- Monitor long-running or import tasks
- Track task name, type, status, progress, file name, and timestamps
- Store error details and import counts
- Useful for CSV product import workflows and async admin operations

### 10. Media and Image Processing
- Auto-process uploaded images using Pillow
- Resize and optimize images for catalog and homepage use
- Store media files in structured directories
- Generate media URLs for frontend consumption

### 11. API Pagination and Filtering
- List product endpoints support pagination
- Search by product name
- Ordering by chosen field
- Block filters and category filters

## API Endpoints

### Authentication
- `POST /register` — Register a new user
- `POST /login` — Login and receive JWT tokens
- `GET /test` — Test endpoint

### Products
- `POST /product` — Add a product with images
- `GET /products` — Get all products
- `GET /get_product/<id>/` — Get a single product by ID
- `GET /block_product` — Get paginated products with optional filters
- `POST /save_blocks` — Save homepage product block assignments
- `GET /get_product_by_block` — Get products by selected block
- `GET /all_blocks` — Get all homepage blocks grouped by block number
- `GET /cat/<name>` — Get products in a category by slug
- `GET /all_cat` — Get all categories

### Contact
- `POST /contact` — Submit a contact message
- `PUT/PATCH /contact/<pk>/` — Update a contact entry

### Front Sections
- `GET /front_sections` — List front sections, optional `?block=<int>` filter
- `POST /front_sections/create` — Create or update a front section

### Multi Image Sections
- `GET /multi_sections` — List multi-image section entries
- `POST /multi_sections/create` — Create or update a multi-image section

### New Section Home Blocks
- `GET /new_section_homeblocks` — List new home blocks
- `POST /new_section_homeblocks/create` — Create or update a new home block

### Background Tasks
- `GET /background_tasks` — View recent background task status

## Main Models

- `User` — custom user model using email as unique login field
- `Category` — product categories
- `Product` — product catalog items
- `ProductImages` — product gallery images
- `HomeBlock` — homepage grouping of products by block
- `Contact` — user inquiries/contact submissions
- `FrontSection` — hero/tooling promotional sections
- `MultiImageSection` — multiple-image section manager
- `SectionImage` — image item for multi-image section
- `NewSectionHomeBlock` — 4-image marketing block
- `BackgroundTask` — background job tracking

## Tech Stack
- Python
- Django
- Django REST Framework
- Django REST Framework SimpleJWT
- Pillow (image processing)
- SQLite database
- Media file uploads

## Summary

This backend API is designed to support a storefront or product showcase website with modern catalog features, homepage customization, media handling, and secure user authentication. It exposes REST endpoints that let the frontend manage products, categories, homepage content, contact records, and promotional image sections.
