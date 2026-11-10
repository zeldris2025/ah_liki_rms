"""Career Connect content, edited in the Django admin with its own model permissions.

Nobody gets these permissions automatically (superusers aside, as with every model): add people to the
'Career Connect Admin' group. The SMS access levels still apply, so only Managers can reach the admin at all.
"""
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Company, CompanyImage, Department, ExpressionOfInterest, PortalSettings, Role
from .templatetags.career_icons import BUSINESS_ICONS, icon


@admin.register(PortalSettings)
class PortalSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_published', 'updated_at', 'public_link')
    fieldsets = (
        (None, {'fields': ('is_published', 'tagline', 'hero_text', 'hero_image', 'company_image')}),
        ('About the company', {'fields': ('company_intro', 'company_background')}),
        ('Headquarters opening video', {'fields': ('video_title', 'video_url', 'video_caption')}),
        ('Headquarters location', {'fields': ('hq_name', 'hq_address', 'hq_directions',
                                              ('hq_latitude', 'hq_longitude'), 'hq_map_url')}),
        ('Contact and applications', {'fields': ('contact_email', 'contact_phone', 'application_instructions')}),
        ('Footer and social media', {'fields': ('footer_slogan', 'footer_closing', 'footer_text',
                                                'facebook_url', 'instagram_url', 'linkedin_url')}),
    )
    autocomplete_fields = ('hero_image', 'company_image')

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not PortalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Public page')
    def public_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">Open Career Connect ↗</a>',
                           reverse('career_connect'))


class DepartmentInline(admin.TabularInline):
    model = Department
    fields = ('name', 'slug', 'order', 'is_published')
    prepopulated_fields = {'slug': ('name',)}
    show_change_link = True
    extra = 0


def _opacity_widget(db_field, kwargs):
    if db_field.name == 'background_opacity':
        kwargs['widget'] = forms.NumberInput(attrs={'min': 10, 'max': 90, 'step': 5, 'style': 'width:6em'})


def _icon_picker(db_field, field):
    """The icon choice as a grid of the icons themselves (styled by career_connect/admin_icons.css)."""
    if db_field.name == 'symbol' and field is not None:
        field.widget = forms.RadioSelect(attrs={'class': 'cc-icon-grid'})
        field.choices = [(key, format_html('{}<span>{}</span>', icon(key, 26), label)) for key, label in BUSINESS_ICONS]
    return field


class IconMedia:
    css = {'all': ('career_connect/admin_icons.css',)}


def _thumbnail(obj):
    if not obj.background:
        return '—'
    return format_html('<img src="{}" alt="" style="height:34px;width:56px;object-fit:cover;border-radius:4px">',
                       obj.background.url)


def _card_preview(obj, default_name, fit='cover'):
    """The card as it appears on the public pages: the colour with the background picture faded over it."""
    p = obj.palette
    inset = '14px' if fit == 'contain' else '0'
    photo = (format_html('<span style="position:absolute;inset:{};background:url(&quot;{}&quot;) center/{} no-repeat;'
                         'opacity:{}"></span>', inset, obj.background.url, fit, obj.photo_opacity)
             if obj.background else '')
    return format_html(
        '<div style="position:relative;width:300px;height:140px;border-radius:8px;overflow:hidden;'
        'background:linear-gradient(120deg,{} 0%,{} 150%);color:#fff;font:600 17px/1.3 sans-serif">{}'
        '<span style="position:absolute;left:16px;bottom:30px;text-shadow:0 1px 6px rgba(0,0,0,.35)">{}</span>'
        '<span style="position:absolute;left:16px;bottom:12px;font-size:12px;font-weight:400">{}</span></div>',
        p['dark'], p['main'], photo, obj.name or default_name,
        f'Photo at {obj.background_opacity}%' if obj.background else 'No photo: colour only')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'thumbnail', 'symbol', 'colour', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'colour', 'description', 'order', 'is_published')}),
        ('Icon', {
            'fields': ('symbol', 'icon_image', 'icon_preview'),
            'description': 'Pick one of the icons, or upload your own (e.g. the company logo) to use instead. '
                           'To go back to the picked icon, tick "Clear" under your own icon and save.',
        }),
        ('Background photo or logo', {
            'fields': ('background', 'background_fit', 'background_opacity', 'card_preview'),
            'description': "Upload the company's logo (or a photo) to show behind its card and page heading. It is "
                           'faded over the company colour (50% by default) so the white text stays easy to read. '
                           'To remove it, tick "Clear" and save.',
        }),
    )
    readonly_fields = ('card_preview', 'icon_preview')
    inlines = [DepartmentInline]
    Media = IconMedia

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        _opacity_widget(db_field, kwargs)
        return _icon_picker(db_field, super().formfield_for_dbfield(db_field, request, **kwargs))

    @admin.display(description='Icon shown (after saving)')
    def icon_preview(self, obj):
        p = obj.palette
        inner = (format_html('<img src="{}" alt="" style="width:100%;height:100%;object-fit:contain;border-radius:50%">',
                             obj.icon_image.url) if obj.icon_image else icon(obj.symbol, 30))
        return format_html('<span style="width:62px;height:62px;border-radius:50%;display:inline-grid;place-items:center;'
                           'color:#fff;background:{};padding:{}">{}</span>',
                           '#fff;border:1px solid #ddd' if obj.icon_image else p['main'],
                           '6px' if obj.icon_image else '0', inner)

    @admin.display(description='Picture')
    def thumbnail(self, obj):
        return _thumbnail(obj)

    @admin.display(description='Preview (after saving)')
    def card_preview(self, obj):
        return _card_preview(obj, 'Company', obj.background_fit)


class RoleInline(admin.TabularInline):
    model = Role
    fields = ('title', 'slug', 'vacancy_status', 'apply_method', 'order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    show_change_link = True
    extra = 0


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'thumbnail', 'symbol', 'colour', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    list_filter = ('company',)
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('company', 'name', 'slug', 'symbol', 'colour', 'description', 'order', 'is_published')}),
        ('Background photo', {
            'fields': ('background', 'background_opacity', 'card_preview'),
            'description': "Upload a photo to show behind this department's card and page heading. It is faded "
                           'over the department colour (50% by default) so the white text stays easy to read. '
                           'To remove it, tick "Clear" and save.',
        }),
    )
    readonly_fields = ('card_preview',)
    inlines = [RoleInline]

    Media = IconMedia

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        _opacity_widget(db_field, kwargs)
        return _icon_picker(db_field, super().formfield_for_dbfield(db_field, request, **kwargs))

    @admin.display(description='Photo')
    def thumbnail(self, obj):
        return _thumbnail(obj)

    @admin.display(description='Preview (after saving)')
    def card_preview(self, obj):
        return _card_preview(obj, 'Department')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'department', 'vacancy_status', 'expires_on', 'apply_method', 'is_published')
    list_filter = ('company', 'department', 'vacancy_status', 'apply_method', 'is_published')
    search_fields = ('title', 'summary')
    prepopulated_fields = {'slug': ('title',)}
    fieldsets = (
        (None, {'fields': ('company', 'department', 'title', 'slug', 'summary', 'order', 'is_published')}),
        ('Job details', {'fields': ('responsibilities', 'qualifications', 'skills'),
                         'description': 'The full job description is not shown publicly: the role page asks '
                                        'students to email hr@ahliki.com for it.'}),
        ('Vacancy and applying', {'fields': ('vacancy_status', 'expires_on', 'how_to_apply', 'apply_method', 'apply_url',
                                             'apply_email')}),
    )


@admin.register(CompanyImage)
class CompanyImageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    search_fields = ('caption', 'alt_text', 'image')


@admin.register(ExpressionOfInterest)
class ExpressionOfInterestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'role_title', 'email', 'phone', 'school', 'created_at', 'reviewed')
    list_filter = ('reviewed', 'role__company', 'role__department', 'created_at')
    list_editable = ('reviewed',)
    search_fields = ('full_name', 'email', 'school', 'role_title')
    readonly_fields = ('role', 'role_title', 'full_name', 'email', 'phone', 'school', 'message', 'created_at')

    def has_add_permission(self, request):
        return False   # they only come from the public form
