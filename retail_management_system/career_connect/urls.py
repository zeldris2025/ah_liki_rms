from django.urls import path

from . import views

urlpatterns = [
    # Public (no sign-in) — every name here is listed in access.PUBLIC_URL_NAMES
    path('career-connect/',                                    views.home,        name='career_connect'),
    path('career-connect/about/',                              views.about,       name='career_connect_about'),
    path('career-connect/careers/',                            views.departments, name='career_connect_departments'),
    path('career-connect/careers/<slug:dept_slug>/',           views.department,  name='career_connect_department'),
    path('career-connect/careers/<slug:dept_slug>/<slug:role_slug>/', views.role, name='career_connect_role'),
    path('career-connect/careers/<slug:dept_slug>/<slug:role_slug>/interest/', views.interest,
         name='career_connect_interest'),
    path('career-connect/images/<int:image_id>/',              views.image,       name='career_connect_image'),
    path('career-connect/images/department/<slug:dept_slug>/', views.department_image,
         name='career_connect_department_image'),
    # Staff only (signed in + permission)
    path('manage/career-connect/qr/',                          views.manage_qr,   name='career_connect_manage_qr'),
]
