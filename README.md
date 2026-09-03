# Ah Liki Wholesale — Sales and Marketing System

## Quick Start

```bash
pip install -r requirements.txt
cd retail_management_system
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit http://127.0.0.1:8000/

## What's New (v2)

- **Photo uploads on every record** — Shops, HORECCA clients, and Sponsorships all support multiple photo uploads.
- **Optional note/label per photo** — Describe what each image shows (e.g. "Storefront", "Business License", "Cooler After Install").
- **Drag-and-drop upload zones** — Click or drag photos into the upload panel on any add/edit form.
- **Lightbox gallery** — Click any photo on the detail page to open a full-screen carousel with label overlay and thumbnail strip.
- **Photos grouped by label** — On the shop detail page, photos are grouped by their note/label for easy navigation.
- **Sponsorships module** — Full CRUD for tracking Signage, Cooler, Event, Vehicle, Uniform, Digital, and Other deals with WST value and status.
- **Dashboard** — Summary stats, bar charts for region and HORECCA type breakdown, and a recent-shops feed.
- **Reports** — Filter and download CSV for Shops, HORECCA, and Sponsorships separately.
- **Refreshed UI** — Deep-navy sidebar, clean card layout, consistent badge/button system throughout.

## Structure

```
retail_management_system/
├── shops/
│   ├── models.py       ← Shop, ShopPhoto, Business, BusinessPhoto, Sponsorship, SponsorshipPhoto
│   ├── views.py        ← All views (dashboard, CRUD, reports)
│   ├── urls.py         ← All URL routes
│   ├── admin.py        ← Admin with photo inlines and previews
│   └── templates/shops/
│       ├── base.html              ← Nav, sidebar, lightbox JS
│       ├── dashboard.html
│       ├── shop_list.html
│       ├── shop_detail.html       ← Photo gallery + grouped labels
│       ├── shop_form.html         ← Add / Edit (with photo panel)
│       ├── island_shops.html      ← Upolu & Savaii region views
│       ├── business_list.html
│       ├── business_form.html
│       ├── sponsorship_list.html
│       ├── sponsorship_form.html
│       ├── reports.html
│       └── photo_upload_panel.html   ← Reusable include
└── retail_management_system/
    ├── settings.py
    └── urls.py
```
