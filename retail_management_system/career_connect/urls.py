from django.urls import path

from . import hr_views, views

urlpatterns = [
    # Public (no sign-in) — every name here is listed in access.PUBLIC_URL_NAMES
    path('career-connect/',                                    views.home,        name='career_connect'),
    path('career-connect/language/',                           views.set_language, name='career_connect_language'),
    path('career-connect/about/',                              views.about,       name='career_connect_about'),
    path('career-connect/careers/',                            views.careers,     name='career_connect_careers'),
    path('career-connect/careers/<slug:company_slug>/',        views.company,     name='career_connect_company'),
    # Roles posted straight to a company (no department); before the department patterns, which would match too
    path('career-connect/careers/<slug:company_slug>/roles/<slug:role_slug>/', views.role,
         name='career_connect_company_role'),
    path('career-connect/careers/<slug:company_slug>/roles/<slug:role_slug>/interest/', views.interest,
         name='career_connect_company_interest'),
    path('career-connect/careers/<slug:company_slug>/<slug:dept_slug>/', views.department,
         name='career_connect_department'),
    path('career-connect/careers/<slug:company_slug>/<slug:dept_slug>/<slug:role_slug>/', views.role,
         name='career_connect_role'),
    path('career-connect/careers/<slug:company_slug>/<slug:dept_slug>/<slug:role_slug>/interest/', views.interest,
         name='career_connect_interest'),
    path('career-connect/jd/<int:role_id>/',                   views.role_jd,     name='career_connect_role_jd'),
    path('career-connect/images/<int:image_id>/',              views.image,       name='career_connect_image'),
    path('career-connect/images/company/<slug:company_slug>/', views.company_image,
         name='career_connect_company_image'),
    path('career-connect/images/icon/<slug:company_slug>/', views.company_icon, name='career_connect_company_icon'),
    path('career-connect/images/department/<slug:company_slug>/<slug:dept_slug>/', views.department_image,
         name='career_connect_department_image'),
    # Staff only (signed in + permission)
    path('manage/career-connect/qr/',                          views.manage_qr,   name='career_connect_manage_qr'),
    # HR (signed in + manage_vacancies) — every name here is listed in access.HR_URL_NAMES
    path('manage/career-connect/',                             hr_views.dashboard,      name='hr_dashboard'),
    path('manage/career-connect/turnover/',                    hr_views.turnover,       name='hr_turnover'),
    path('manage/career-connect/vacancies/',                   hr_views.vacancies,      name='hr_vacancies'),
    path('manage/career-connect/vacancies/new/',               hr_views.vacancy_add,    name='hr_vacancy_add'),
    path('manage/career-connect/vacancies/<int:role_id>/',     hr_views.vacancy_edit,   name='hr_vacancy_edit'),
    path('manage/career-connect/vacancies/<int:role_id>/status/', hr_views.vacancy_status, name='hr_vacancy_status'),
    path('manage/career-connect/vacancies/<int:role_id>/delete/', hr_views.vacancy_delete, name='hr_vacancy_delete'),
    path('manage/career-connect/vacancies/<int:role_id>/applications/', hr_views.applications, name='hr_applications'),
    path('manage/career-connect/applications/<int:app_id>/reviewed/', hr_views.application_reviewed,
         name='hr_application_reviewed'),
    path('manage/career-connect/applications/<int:app_id>/stage/', hr_views.application_stage,
         name='hr_application_stage'),
    path('manage/career-connect/applications/<int:app_id>/<str:kind>/', hr_views.application_file,
         name='hr_application_file'),
]
