# CSV Import Feature Documentation

## Overview
Added bulk CSV import functionality for **Shops**, **HORECA Businesses**, and **Sponsorships** to quickly add multiple records at once.

## Features

### 1. **Django Admin Integration**
The most powerful method for importing data. Uses `django-import-export` library:
- Navigate to Django Admin → Shops/Businesses/Sponsorships
- Click **"Import"** button in the top-right corner
- Upload your CSV file and preview before importing
- Full validation with detailed error reporting

### 2. **Frontend Web Interface**
User-friendly web forms for importing data:
- Located in the sidebar under "Bulk Import" section
- Three separate import pages:
  - `/import/shops/` — Import retail shops
  - `/import/businesses/` — Import HORECA businesses
  - `/import/sponsorships/` — Import sponsorships
- Download CSV templates directly from each page
- Error messages with details on what went wrong

### 3. **CSV Templates**
Pre-formatted templates available for download:
- `/templates/shops/` — Download shops template
- `/templates/businesses/` — Download HORECA template
- `/templates/sponsorships/` — Download sponsorships template

## CSV Format Requirements

### Shops (shops_template.csv)
```csv
name,owner,phone,address,island,territory,tip_top,taula_fridge,talofa_voucher,faakau_com,products,quantity,total_sales,date
My Shop,John Doe,+685-1234567,123 Main Street,Upolu,EC1,FALSE,FALSE,FALSE,FALSE,Coca Cola 1.5L,24,120.00,2026-01-15
```

**Fields:**
- `name` (required) — Shop name
- `owner` — Owner name
- `phone` — Phone number
- `address` — Shop address
- `island` — "Upolu" or "Savaii"
- `territory` — EC1, EC2, EC3, LFG, VT1, VT2, VT3, WC1, WC2, or WC4
- `tip_top` — TRUE or FALSE (boolean)
- `taula_fridge` — TRUE or FALSE (boolean)
- `talofa_voucher` — TRUE or FALSE (boolean)
- `faakau_com` — TRUE or FALSE (boolean)
- `products`, `quantity`, `total_sales`, `date` — optional sales record for the shop

**Matching by name:** a row whose `name` matches an existing shop (case-insensitive) never
creates a duplicate. Every field in the row is compared against the shop on record and only the
differing fields are updated; a row where everything already matches is skipped. Blank cells and
columns omitted from your file are ignored, so they never wipe existing values.

### HORECA Businesses (horecca_template.csv)
```csv
name,business_type,island,location
Example Hotel,HOTEL,Upolu,Apia
```

**Fields:**
- `name` (required) — Business name
- `business_type` — "HOTEL", "CAFE", "RESTAURANT", or "OTHER"
- `island` — "Upolu" or "Savaii"
- `location` — Location/address

### Sponsorships (sponsorship_template.csv)
```csv
customer,type,value,status,start,end,notes
Company Name,Signage,5000,Active,2026-01-01,2026-12-31,Annual sponsorship
```

**Fields:**
- `customer` (required) — Company/person name
- `type` — "Signage", "Cooler", "Event", "Vehicle", "Uniform", "Digital", "Other"
- `value` — Numeric value (WST currency)
- `status` — "Active", "Expired", or "Pending"
- `start` — Start date (YYYY-MM-DD format)
- `end` — End date (YYYY-MM-DD format)
- `notes` — Additional notes

## Usage Guide

### Method 1: Admin Interface (Recommended)
1. Log in to Django Admin (`/admin/`)
2. Go to Shops, HORECCA Clients, or Sponsorships section
3. Click the **"Import data"** button
4. Upload your CSV file
5. Review the preview
6. Click **"Confirm import"** to proceed

### Method 2: Web Forms
1. Log in to the RMS application
2. Go to the sidebar → **Bulk Import** section
3. Click the appropriate import link (Shops/HORECCA/Sponsorships)
4. Download the template CSV (recommended)
5. Fill in your data using the template format
6. Upload the CSV file
7. View import results on the next page

## Tips & Best Practices

✅ **Do:**
- Download and use the provided CSV templates
- Use proper date format (YYYY-MM-DD) for date fields
- Verify all data before importing
- Start with a small test import to verify format
- Use only valid choices for dropdown fields

❌ **Don't:**
- Leave required fields empty
- Use inconsistent formats for dates
- Include extra columns not in the schema
- Use special characters in field values (unless necessary)

## Technical Details

### Installation & Dependencies
The feature uses `django-import-export` (already in requirements.txt):
```bash
pip install django-import-export>=3.0
```

### Files Modified/Created

**Modified:**
- `shops/admin.py` — Added ImportExportModelAdmin and Resource classes
- `shops/forms.py` — Added CSV import forms
- `shops/views.py` — Added import views and template download views
- `shops/urls.py` — Added URL patterns for import routes
- `shops/templates/shops/base.html` — Added navigation links

**Created:**
- `shops/templates/shops/import_shops.html` — Shops import form
- `shops/templates/shops/import_businesses.html` — HORECA import form
- `shops/templates/shops/import_sponsorships.html` — Sponsorships import form
- `shops/templates/shops/import_result.html` — Import results page

### URL Routes
```
/import/shops/              — Shops import form
/import/businesses/         — HORECA import form
/import/sponsorships/       — Sponsorships import form
/templates/shops/           — Download shops template
/templates/businesses/      — Download HORECA template
/templates/sponsorships/    — Download sponsorships template
```

## Error Handling

The system provides detailed error messages:
- **Validation errors** — Shows which rows/fields failed validation
- **Format errors** — Indicates incorrect data types (e.g., wrong date format)
- **Choice errors** — Shows invalid choices for dropdown fields
- **Required field errors** — Indicates missing required fields

## Support for Future Enhancements

Potential improvements that can be added:
- Drag-and-drop file upload
- CSV data preview before import
- Bulk edit functionality
- Scheduled/automated imports
- Export to CSV with filters
- Duplicate detection and handling
