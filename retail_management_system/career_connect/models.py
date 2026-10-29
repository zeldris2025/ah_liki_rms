"""Ah Liki Career Connect: public company information and career pages for students.

Companies (Ah Liki Investment group) → departments → roles. Everything shown publicly is typed in by an administrator; blank fields show 'not provided yet' rather than
made-up text. Only published departments, roles and images ever reach the public pages.
"""
import os
import re
from urllib.parse import parse_qs, quote, urlparse

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


class PortalSettings(models.Model):
    """The single row of portal-wide content (company information, video, headquarters, contact)."""
    is_published = models.BooleanField(
        'portal is visible to the public', default=True,
        help_text='Untick to take every public Career Connect page offline (the QR code then shows "not available").')
    tagline = models.CharField(max_length=200, default='Discover Opportunities. Build Your Future.')
    hero_text = models.CharField(
        'hero text', max_length=300,
        default='Explore our departments, discover career opportunities, and learn more about Ah Liki Wholesale.')
    hero_image = models.ForeignKey(
        'CompanyImage', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text='The large photo at the top of the home page (a published company photo, e.g. the headquarters).')
    company_image = models.ForeignKey(
        'CompanyImage', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text='The photo beside "Our Company" on the home page.')

    company_intro = models.TextField('company introduction', blank=True)
    company_background = models.TextField('company background / history', blank=True)

    video_title = models.CharField(max_length=200, default='Ah Liki Wholesale Headquarters Opening (2021)')
    video_url = models.URLField(
        'video link', blank=True,
        help_text='A YouTube, Vimeo or Facebook video link. Other links are shown as a "Watch the video" button.')
    video_caption = models.TextField(blank=True)

    hq_name = models.CharField('headquarters name', max_length=200, blank=True)
    hq_address = models.TextField('headquarters address', blank=True)
    hq_directions = models.TextField('directions', blank=True, help_text='Landmarks, bus routes, parking, etc.')
    hq_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    hq_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    hq_map_url = models.URLField('map link', blank=True,
                                 help_text='Optional: a Google Maps link. Without it, latitude/longitude are used.')

    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=60, blank=True)
    application_instructions = models.TextField(
        'general application instructions', blank=True,
        help_text='Shown on every role page that has no instructions of its own.')
    footer_text = models.TextField(blank=True, help_text='Extra line in the footer, e.g. opening hours.')
    footer_slogan = models.CharField(max_length=120, blank=True, help_text='Under the logo in the footer.')
    footer_closing = models.CharField(max_length=160, blank=True, help_text='Bottom-right line of the footer.')
    facebook_url = models.URLField('Facebook page', blank=True)
    instagram_url = models.URLField('Instagram page', blank=True)
    linkedin_url = models.URLField('LinkedIn page', blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = 'portal settings'
        permissions = [('manage_career_connect', 'Can manage Career Connect and print its QR code')]

    def __str__(self):
        return 'Career Connect portal settings'

    def save(self, *args, **kwargs):
        self.pk = 1   # only ever one row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def video_embed_url(self):
        """An embeddable player address for YouTube / Vimeo / Facebook links, else ''."""
        return video_embed_url(self.video_url)

    @property
    def hero_image_url(self):
        return _published_url(self.hero_image)

    @property
    def company_image_url(self):
        return _published_url(self.company_image)

    @property
    def social_links(self):
        return [(name, url) for name, url in (('facebook', self.facebook_url), ('instagram', self.instagram_url),
                                              ('linkedin', self.linkedin_url)) if url]

    @property
    def directions_url(self):
        if self.hq_map_url:
            return self.hq_map_url
        if self.hq_latitude is not None and self.hq_longitude is not None:
            return f'https://www.google.com/maps/dir/?api=1&destination={self.hq_latitude},{self.hq_longitude}'
        if self.hq_address:
            return 'https://www.google.com/maps/search/?api=1&query=' + quote(' '.join(self.hq_address.split()))
        return ''

    @property
    def map_embed_url(self):
        """An OpenStreetMap embed (no API key) when coordinates are set."""
        if self.hq_latitude is None or self.hq_longitude is None:
            return ''
        lat, lon, d = float(self.hq_latitude), float(self.hq_longitude), 0.006
        return ('https://www.openstreetmap.org/export/embed.html?bbox='
                f'{lon - d:.6f},{lat - d:.6f},{lon + d:.6f},{lat + d:.6f}&layer=mapnik&marker={lat:.6f},{lon:.6f}')


def _published_url(image):
    """The public address of a company photo, or '' if none is chosen or it isn't published."""
    return image.get_absolute_url() if image is not None and image.is_published else ''


_YOUTUBE_ID = re.compile(r'^[A-Za-z0-9_-]{6,20}$')


def video_embed_url(url):
    if not url:
        return ''
    u = urlparse(url)
    if u.scheme not in ('http', 'https'):
        return ''
    host = (u.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    video_id = ''
    if host == 'youtu.be':
        video_id = u.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'youtube-nocookie.com'):
        if u.path == '/watch':
            video_id = parse_qs(u.query).get('v', [''])[0]
        elif u.path.startswith(('/embed/', '/shorts/', '/live/')):
            video_id = u.path.split('/')[2]
    if video_id:
        return f'https://www.youtube-nocookie.com/embed/{video_id}' if _YOUTUBE_ID.match(video_id) else ''
    if host == 'vimeo.com':
        first = u.path.strip('/').split('/')[0]
        return f'https://player.vimeo.com/video/{first}' if first.isdigit() else ''
    if host in ('facebook.com', 'fb.watch'):
        return 'https://www.facebook.com/plugins/video.php?show_text=false&href=' + quote(url, safe='')
    return ''


PHOTO_TYPES = ['jpg', 'jpeg', 'png', 'webp']
MAX_PHOTO_MB = 8


def _photo_size(file):
    if file.size > MAX_PHOTO_MB * 1024 * 1024:
        raise ValidationError(f'The photo must be smaller than {MAX_PHOTO_MB} MB.')


def _photo_opacity(percent):
    """A photo-strength percentage as a CSS opacity, kept within 10–90%."""
    return f'{min(max(percent, 10), 90) / 100:.2f}'


class CompanyImage(models.Model):
    image = models.ImageField(upload_to='career_connect/',
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp', 'gif'])])
    caption = models.CharField(max_length=200, blank=True)
    alt_text = models.CharField('description for screen readers', max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.caption or self.image.name

    def get_absolute_url(self):
        return reverse('career_connect_image', args=[self.pk])


class Company(models.Model):
    """A company in the Ah Liki Investment group. Its departments (and their roles) are listed on its careers page."""
    COLOURS = {
        'blue':   ('#1E6FE0', '#0B3F8F', '#E3EEFD'),
        'purple': ('#7C3AED', '#4C1D95', '#EEE7FD'),
        'orange': ('#F07A1A', '#9A3F07', '#FDEBDC'),
        'green':  ('#16A34A', '#0F5D2E', '#DDF5E5'),
        'teal':   ('#0E9BB5', '#0A5566', '#DCF3F7'),
        'navy':   ('#1E40AF', '#0B1F4D', '#E2E8F7'),
        'red':    ('#DC2626', '#7F1D1D', '#FDE4E4'),
    }
    COLOUR_CHOICES = [(k, k.title()) for k in COLOURS]
    SYMBOL_CHOICES = [('store', 'Store (wholesale / retail)'), ('cart', 'Cart (supermarket)'),
                      ('utensils', 'Utensils (food)'), ('leaf', 'Leaf (farm)'), ('building', 'Building')]
    FIT_CHOICES = [('contain', 'Whole picture, centred (best for logos)'), ('cover', 'Fill the card (best for photos)')]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True, help_text='Used in the web address, e.g. "farmer-joe".')
    symbol = models.CharField('icon', max_length=20, choices=SYMBOL_CHOICES, default='building')
    colour = models.CharField(max_length=20, choices=COLOUR_CHOICES, default='navy')
    background = models.ImageField(
        'background photo or logo', upload_to='career_connect/companies/', blank=True,
        validators=[FileExtensionValidator(PHOTO_TYPES), _photo_size],
        help_text=f'Optional. Shown faded behind the company card and page heading (JPG, PNG or WebP, under {MAX_PHOTO_MB} MB).')
    background_fit = models.CharField('picture fit', max_length=10, choices=FIT_CHOICES, default='contain')
    background_opacity = models.PositiveSmallIntegerField(
        'photo strength (%)', default=50, validators=[MinValueValidator(10), MaxValueValidator(90)],
        help_text='How strongly the picture shows over the company colour: 50 = half faded (recommended).')
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ('order', 'name')
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('career_connect_company', args=[self.slug])

    @property
    def image_url(self):
        """The public address of the background picture ('' if none), with ?v= as for departments."""
        if not self.background:
            return ''
        return (reverse('career_connect_company_image', args=[self.slug])
                + '?v=' + quote(os.path.basename(self.background.name)))

    @property
    def photo_opacity(self):
        return _photo_opacity(self.background_opacity)

    @property
    def palette(self):
        main, dark, soft = self.COLOURS.get(self.colour, self.COLOURS['navy'])
        return {'main': main, 'dark': dark, 'soft': soft}


class Department(models.Model):
    # Card colours: (main, dark, soft tint)
    COLOURS = {
        'blue':   ('#1E6FE0', '#0B3F8F', '#E3EEFD'),
        'purple': ('#7C3AED', '#4C1D95', '#EEE7FD'),
        'orange': ('#F07A1A', '#9A3F07', '#FDEBDC'),
        'green':  ('#16A34A', '#0F5D2E', '#DDF5E5'),
        'teal':   ('#0E9BB5', '#0A5566', '#DCF3F7'),
        'navy':   ('#1E40AF', '#0B1F4D', '#E2E8F7'),
    }
    COLOUR_CHOICES = [(k, k.title()) for k in COLOURS]
    SYMBOL_CHOICES = [('coins', 'Coins (finance)'), ('megaphone', 'Megaphone (marketing)'), ('people', 'People (HR)'),
                      ('chart', 'Chart (sales)'), ('box', 'Box (warehouse)'), ('wrench', 'Wrench (trades)'),
                      ('briefcase', 'Briefcase')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='departments')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, help_text='Used in the web address, e.g. "finance"; unique within the company.')
    symbol = models.CharField('icon', max_length=20, choices=SYMBOL_CHOICES, default='briefcase')
    colour = models.CharField(max_length=20, choices=COLOUR_CHOICES, default='blue')
    background = models.ImageField(
        'background photo', upload_to='career_connect/departments/', blank=True,
        validators=[FileExtensionValidator(PHOTO_TYPES), _photo_size],
        help_text=f'Optional. Shown faded behind the department card and page heading (JPG, PNG or WebP, under {MAX_PHOTO_MB} MB).')
    background_opacity = models.PositiveSmallIntegerField(
        'photo strength (%)', default=50, validators=[MinValueValidator(10), MaxValueValidator(90)],
        help_text='How strongly the photo shows over the department colour: 50 = half faded (recommended).')
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ('company__order', 'order', 'name')
        constraints = [models.UniqueConstraint(fields=('company', 'slug'), name='career_department_unique_slug')]

    def __str__(self):
        return f'{self.name} ({self.company})'

    def get_absolute_url(self):
        return reverse('career_connect_department', args=[self.company.slug, self.slug])

    @property
    def image_url(self):
        """The public address of the background photo ('' if none). The file name in ?v= refreshes browsers' copies
        when a new photo is uploaded."""
        if not self.background:
            return ''
        return (reverse('career_connect_department_image', args=[self.company.slug, self.slug])
                + '?v=' + quote(os.path.basename(self.background.name)))

    @property
    def photo_opacity(self):
        return _photo_opacity(self.background_opacity)

    @property
    def palette(self):
        main, dark, soft = self.COLOURS.get(self.colour, self.COLOURS['blue'])
        return {'main': main, 'dark': dark, 'soft': soft}


class Role(models.Model):
    NOT_STATED, OPEN, CLOSED = 'not_stated', 'open', 'closed'
    VACANCY_CHOICES = [
        (NOT_STATED, 'Not stated'),
        (OPEN, 'Currently recruiting'),
        (CLOSED, 'Not currently recruiting'),
    ]
    APPLY_NONE, APPLY_FORM, APPLY_LINK, APPLY_EMAIL = 'none', 'interest_form', 'external_link', 'email'
    APPLY_CHOICES = [
        (APPLY_NONE, 'No apply button'),
        (APPLY_FORM, 'Expression-of-interest form on this page'),
        (APPLY_LINK, 'Button to an external application link'),
        (APPLY_EMAIL, 'Button that emails the application address'),
    ]

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='roles')
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, help_text='Used in the web address; unique within the department.')
    summary = models.CharField(max_length=300, blank=True, help_text='One line shown on the department page.')
    description = models.TextField('job description', blank=True)
    responsibilities = models.TextField(blank=True, help_text='One per line.')
    qualifications = models.TextField('required qualifications', blank=True, help_text='One per line.')
    skills = models.TextField('skills', blank=True, help_text='One per line.')
    vacancy_status = models.CharField(max_length=20, choices=VACANCY_CHOICES, default=NOT_STATED)
    how_to_apply = models.TextField('application instructions', blank=True,
                                    help_text='Leave blank to use the general instructions from the portal settings.')
    apply_method = models.CharField('apply button', max_length=20, choices=APPLY_CHOICES, default=APPLY_NONE)
    apply_url = models.URLField('external application link', blank=True)
    apply_email = models.EmailField('application email', blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ('department__company__order', 'department__order', 'order', 'title')
        constraints = [models.UniqueConstraint(fields=('department', 'slug'), name='career_role_unique_slug')]
        permissions = [('manage_vacancies', 'Can post and update vacancies on the HR vacancies page')]

    def __str__(self):
        return f'{self.title} ({self.department})'

    def get_absolute_url(self):
        return reverse('career_connect_role', args=[self.department.company.slug, self.department.slug, self.slug])

    @staticmethod
    def _lines(text):
        return [line.strip(' -•*\t') for line in text.splitlines() if line.strip(' -•*\t')]

    @property
    def responsibility_list(self):
        return self._lines(self.responsibilities)

    @property
    def qualification_list(self):
        return self._lines(self.qualifications)

    @property
    def skill_list(self):
        return self._lines(self.skills)

    @property
    def accepts_interest(self):
        return self.apply_method == self.APPLY_FORM


class ExpressionOfInterest(models.Model):
    """A student's interest in a role, sent from the public form. Only visible in the admin."""
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, related_name='interests')
    role_title = models.CharField(max_length=150, help_text='Kept in case the role is later deleted.')
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    school = models.CharField('school / institution', max_length=150, blank=True)
    message = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'expression of interest'
        verbose_name_plural = 'expressions of interest'

    def __str__(self):
        return f'{self.full_name} — {self.role_title}'
