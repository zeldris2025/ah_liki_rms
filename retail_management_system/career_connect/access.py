"""The public side of Career Connect: the only URL names anyone may open without signing in.

Students reach these by scanning the QR code. They're also opened up for the FE and Finance access levels (whose
middleware otherwise only allows a fixed list), so a signed-in staff member who scans the code still sees the portal.
Nothing here reads request.user, and the management pages (the QR page, the Django admin) are not in this list.
"""

PUBLIC_URL_NAMES = {
    'career_connect',
    'career_connect_about',
    'career_connect_careers',
    'career_connect_company',
    'career_connect_department',
    'career_connect_role',
    'career_connect_interest',
    'career_connect_company_role',
    'career_connect_company_interest',
    'career_connect_image',
    'career_connect_company_image',
    'career_connect_company_icon',
    'career_connect_role_jd',
    'career_connect_department_image',
}

# Who may print the QR code and see the Career Connect link in the sidebar (content itself is edited in the admin
# with the usual per-model permissions). Nobody gets it automatically: add people to the 'Career Connect Admin' group.
MANAGE_PERMISSION = 'career_connect.manage_career_connect'

# HR: posts and updates the vacancies (roles) of every company on the HR vacancies page. People in the 'HR' group
# (and no office level) are an access level of their own: they only get these pages plus the public portal.
HR_GROUP = 'HR'
VACANCY_PERMISSION = 'career_connect.manage_vacancies'
HR_URL_NAMES = {'hr_vacancies', 'hr_vacancy_add', 'hr_vacancy_edit', 'hr_vacancy_status', 'hr_vacancy_delete',
                'hr_applications', 'hr_application_reviewed', 'hr_application_file'}
HR_ALLOWED = {'login', 'logout'} | HR_URL_NAMES | PUBLIC_URL_NAMES
# The one download HR may make (they can't export anything else): an applicant's CV, cover letter or qualifications
HR_DOWNLOADS = {'hr_application_file'}
