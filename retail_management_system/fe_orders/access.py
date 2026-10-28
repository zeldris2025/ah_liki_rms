"""The fe_boys access level: field executives who only see the FE screens and the atlas."""
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from career_connect.access import PUBLIC_URL_NAMES as CAREER_CONNECT_PUBLIC

FE_GROUP = 'fe_boys'

# URL names an FE user may open; everything else sends them back to the FE home.
# The public Career Connect pages are open to everyone, signed in or not.
FE_ALLOWED = {'login', 'logout', 'atlas', 'atlas_shop_location'} | CAREER_CONNECT_PUBLIC


def is_fe(user):
    return (user.is_authenticated and not user.is_superuser
            and user.groups.filter(name=FE_GROUP).exists())


class FEAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_fe = is_fe(request.user)
        if request.is_fe and not self._allowed(request.path_info):
            return redirect('fe_home')
        return self.get_response(request)

    @staticmethod
    def _allowed(path):
        from django.conf import settings
        if path.startswith((settings.STATIC_URL, settings.MEDIA_URL)):
            return True
        try:
            name = resolve(path).url_name or ''
        except Resolver404:
            return True   # let Django render its normal 404
        return name.startswith('fe_') or name in FE_ALLOWED


def fe_context(request):
    return {'is_fe': getattr(request, 'is_fe', False)}
