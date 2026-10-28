"""The public side of Career Connect: the only URL names anyone may open without signing in.

Students reach these by scanning the QR code. They're also opened up for the FE and Finance access levels (whose
middleware otherwise only allows a fixed list), so a signed-in staff member who scans the code still sees the portal.
Nothing here reads request.user, and the management pages (the QR page, the Django admin) are not in this list.
"""

PUBLIC_URL_NAMES = {
    'career_connect',
    'career_connect_about',
    'career_connect_departments',
    'career_connect_department',
    'career_connect_role',
    'career_connect_interest',
    'career_connect_image',
    'career_connect_department_image',
}

# Who may print the QR code and see the Career Connect link in the sidebar (content itself is edited in the admin
# with the usual per-model permissions). Nobody gets it automatically: add people to the 'Career Connect Admin' group.
MANAGE_PERMISSION = 'career_connect.manage_career_connect'
