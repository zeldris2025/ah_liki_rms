from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('atlas/', include('retail_atlas.urls')),
    path('', include('fe_orders.urls')),
    path('', include('shops.urls')),
    path('', include('car_allocations.urls')),
    # Uploaded photos (shops, HORECA, sponsorships, FE issues): signed-in users only, also in production
    re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), login_required(serve),
            {'document_root': settings.MEDIA_ROOT}, name='media'),
]
