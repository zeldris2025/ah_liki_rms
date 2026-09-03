# CSV Import - Quick Start Guide

## ✅ Setup Complete!

Your Ah Liki RMS now has full CSV import functionality for:
- 🏪 **Shops** — Import retail shops in bulk
- 🏨 **HORECA Businesses** — Import hotels, cafes, restaurants
- 🤝 **Sponsorships** — Import sponsorship agreements quickly

---

## 🚀 How to Use

### Option 1: Admin Interface (Best for Power Users)
This is the most robust method with full preview and validation.

1. Go to **Django Admin** → `/admin/`
2. Navigate to **Shops**, **HORECA Clients**, or **Sponsorships**
3. Click the **"Import data"** button (top right)
4. Upload your CSV file
5. Review the preview
6. Confirm import

**Advantages:** Full validation, error reporting, preview before import, easy bulk operations

### Option 2: Web Forms (Best for Regular Users)
User-friendly interface within the RMS dashboard.

1. Log in to RMS dashboard
2. In the left sidebar, find **"Bulk Import"** section
3. Click the import type you need:
   - **Import Shops**
   - **Import HORECCA**
   - **Import Sponsorships**
4. Download the CSV template (recommended)
5. Fill in your data
6. Upload the file
7. View import results

**Advantages:** User-friendly, built-in templates, step-by-step guidance

---

## 📋 CSV Format

### Shops CSV
```csv
name,owner,phone,address,island,territory,tip_top,taula_fridge,talofa_voucher,faakau_com
My Shop,John Doe,+685-7123456,123 Main St,Upolu,EC1,TRUE,FALSE,TRUE,TRUE
```

**Required:** `name`  
**Optional:** owner, phone, address, island, territory, tip_top, taula_fridge, talofa_voucher, faakau_com

**Existing names are updated, not duplicated** — a row matching an existing shop name is compared
field by field and only the differing fields are updated. Rows that already match exactly are skipped.
Blank cells and omitted columns are left untouched.

### HORECA CSV
```csv
name,business_type,island,location
Example Hotel,HOTEL,Upolu,Apia
```

**Required:** `name`  
**Optional:** business_type (HOTEL/CAFE/RESTAURANT/OTHER), island, location

### Sponsorships CSV
```csv
customer,type,value,status,start,end,notes
Company,Signage,5000,Active,2026-01-01,2026-12-31,Notes here
```

**Required:** `customer`  
**Optional:** type, value, status, start (YYYY-MM-DD), end (YYYY-MM-DD), notes

---

## 📥 Download Templates

Download pre-formatted CSV templates from the import pages:
- `/import/shops/` → Download shops template
- `/import/businesses/` → Download HORECA template
- `/import/sponsorships/` → Download sponsorships template

Or download sample files from the root directory:
- `sample_shops.csv`
- `sample_businesses.csv`
- `sample_sponsorships.csv`

---

## ✅ Tips for Success

1. **Use Templates** — Download the template to ensure correct format
2. **Test First** — Try importing 1-2 records before bulk import
3. **Check Data** — Verify dates are in YYYY-MM-DD format
4. **Valid Choices** — Use exact values for dropdowns (e.g., "EC1", not "ec 1")
5. **Read Errors** — If import fails, check error messages for specific fields

---

## 🔑 Field Value Reference

### Island (Shops & Businesses)
- `Upolu`
- `Savaii`

### Region (Shops)
- `Region 1`
- `Region 2`
- `Region 3`
- `Region 4`

### Business Type (HORECA)
- `HOTEL`
- `CAFE`
- `RESTAURANT`
- `OTHER`

### Sponsorship Type
- `Signage`
- `Cooler`
- `Event`
- `Vehicle`
- `Uniform`
- `Digital`
- `Other`

### Sponsorship Status
- `Active`
- `Expired`
- `Pending`

---

## 🔗 URL Routes

| Purpose | URL |
|---------|-----|
| Import Shops Form | `/import/shops/` |
| Import HORECA Form | `/import/businesses/` |
| Import Sponsorships Form | `/import/sponsorships/` |
| Download Shops Template | `/templates/shops/` |
| Download HORECA Template | `/templates/businesses/` |
| Download Sponsorship Template | `/templates/sponsorships/` |
| Django Admin Import | `/admin/shops/shop/` |

---

## ❓ Common Issues & Solutions

**Issue:** "Date format not valid"
- **Solution:** Use YYYY-MM-DD format (e.g., 2026-01-15)

**Issue:** "Invalid choice for [field]"
- **Solution:** Check the field value reference above - use exact text

**Issue:** "This field is required"
- **Solution:** Fill in required fields (name for Shops/Sponsorships)

**Issue:** Multiple imports showing duplicate data
- **Solution:** The system doesn't prevent duplicates - check your CSV first

---

## 📚 Sample Data

Three sample CSV files included in the root directory:
- `sample_shops.csv` — 8 shops across both islands
- `sample_businesses.csv` — 12 HORECA businesses
- `sample_sponsorships.csv` — 9 sponsorships

Great for testing the import functionality!

---

## 🔧 Technical Info

- **Technology:** django-import-export (>=3.0)
- **Format:** CSV (Comma-Separated Values)
- **Encoding:** UTF-8 recommended
- **Admin Integration:** Yes (Django admin toolbar)
- **Web Forms:** Yes (RMS dashboard)

---

**For full documentation, see:** `CSV_IMPORT_DOCUMENTATION.md`
