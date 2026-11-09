"""The Product QTY Sales access level: people in the 'Product QTY Sales' group (and no office, Finance, HR or Social level) upload and follow
quantity sales. Inside the SMS they only get the QTY dashboard, the analytics and Product QTY, and they can
download its CSV reports. Nobody is added to the group automatically. Managers (and admins) can open these pages too."""

AJ_GROUP = 'Product QTY Sales'
AJ_URL_NAMES = {'aj_analytics', 'aj_product_qty', 'aj_import', 'aj_template',
                'aj_pin', 'aj_targets', 'aj_group_add', 'aj_group_edit'}
