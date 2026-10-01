from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('atlas/', include('retail_atlas.urls')),
    path('', include('fe_orders.urls')),
    path('', include('shops.urls')),
    path('', include('car_allocations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
