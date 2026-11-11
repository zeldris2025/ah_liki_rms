"""Ah Liki Career Connect: public company information and career pages for students.

Companies (Ah Liki Investment group) → departments → roles. Everything shown publicly is typed in by an administrator; blank fields show 'not provided yet' rather than
made-up text. Only published departments, roles and images ever reach the public pages.
"""
import os
from datetime import timedelta
from decimal import Decimal
import re
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator, validate_email
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.deconstruct import deconstructible
from django.urls import reverse
from django.utils import timezone

from .templatetags.career_icons import BUSINESS_ICONS

# The web address segment for roles posted without a department: /careers/<company>/roles/<role>/
COMPANY_ROLES_PATH = 'roles'


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
    application_emails = models.TextField(
        'send applications to', blank=True, default='charliea@ahliki.com',
        help_text='Who gets an email with each new application (and its CV, cover letter and qualifications). '
                  'One address per line, or separated by commas. Leave empty to stop the emails.')
    application_sender = models.EmailField(
        'send applications from', default='agent@ahliki.com',
        help_text='The Microsoft 365 mailbox the application emails are sent from.')
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

    def clean(self):
        for address in self.application_email_list:
            try:
                validate_email(address)
            except ValidationError:
                raise ValidationError({'application_emails': f'"{address}" is not an email address.'})

    @property
    def application_email_list(self):
        return [a.strip() for a in re.split(r'[,;\s]+', self.application_emails or '') if a.strip()]

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


MAX_ICON_MB = 2
MAX_JD_MB = 10


def _jd_size(file):
    if file.size > MAX_JD_MB * 1024 * 1024:
        raise ValidationError(f'The job description must be smaller than {MAX_JD_MB} MB.')


def _icon_size(file):
    if file.size > MAX_ICON_MB * 1024 * 1024:
        raise ValidationError(f'The icon must be smaller than {MAX_ICON_MB} MB.')


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
    """A company in the Ah Liki Investment group. Its departments (and their roles) are listed on its careers page,
    and so are any roles posted straight to the company (companies without departments)."""
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
    FIT_CHOICES = [('contain', 'Whole picture, centred (best for logos)'), ('cover', 'Fill the card (best for photos)')]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True, help_text='Used in the web address, e.g. "farmer-joe".')
    symbol = models.CharField('icon', max_length=20, choices=BUSINESS_ICONS, default='building')
    icon_image = models.ImageField(
        'own icon', upload_to='career_connect/icons/', blank=True,
        validators=[FileExtensionValidator(PHOTO_TYPES), _icon_size],
        help_text=f'Optional. Upload your own icon (e.g. the logo) to use instead of the one chosen above: a square '
                  f'JPG, PNG or WebP under {MAX_ICON_MB} MB, shown in a white circle.')
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
    employee_count = models.PositiveIntegerField(
        'number of employees', null=True, blank=True, validators=[MinValueValidator(1)],
        help_text='Used for the staff turnover %. It stays the same until HR change it.')

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
    def icon_url(self):
        """The public address of the uploaded icon ('' if none), with ?v= so a new upload shows straight away."""
        if not self.icon_image:
            return ''
        return (reverse('career_connect_company_icon', args=[self.slug])
                + '?v=' + quote(os.path.basename(self.icon_image.name)))

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

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='departments')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, help_text='Used in the web address, e.g. "finance"; unique within the company.')
    symbol = models.CharField('icon', max_length=20, choices=BUSINESS_ICONS, default='briefcase')
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

    def clean(self):
        if self.slug == COMPANY_ROLES_PATH:
            raise ValidationError({'slug': f'"{COMPANY_ROLES_PATH}" is kept for roles posted without a department.'})

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


def office_today():
    """Today's date in the office (Samoa), which is when expiry dates take effect."""
    return timezone.localdate(timezone=ZoneInfo(settings.CAREER_CONNECT_TIME_ZONE))


def live_roles_q(prefix=''):
    """Roles students can see: published and not past their expiry date. prefix='roles__' etc. for related lookups."""
    return (Q(**{f'{prefix}is_published': True})
            & (Q(**{f'{prefix}expires_on__isnull': True}) | Q(**{f'{prefix}expires_on__gt': office_today()})))


def recruiting_q(status):
    """Roles whose recruiting status (see Role.recruiting_status) is `status`, as a database filter."""
    today = office_today()
    dated, undated = Q(expires_on__isnull=False), Q(expires_on__isnull=True)
    if status == 'open':
        return (dated & Q(expires_on__gt=today)) | (undated & Q(vacancy_status=status))
    if status == 'closed':
        return (dated & Q(expires_on__lte=today)) | (undated & Q(vacancy_status=status))
    return undated & Q(vacancy_status=status)


def public_roles_q(prefix=''):
    """Roles students can see on the site: live, in a published company, and in a published department if they have
    one (roles posted without a department sit straight on the company page)."""
    return (live_roles_q(prefix) & Q(**{f'{prefix}company__is_published': True})
            & (Q(**{f'{prefix}department__isnull': True}) | Q(**{f'{prefix}department__is_published': True})))


class RoleQuerySet(models.QuerySet):
    def live(self):
        return self.filter(live_roles_q())

    def public(self):
        return self.filter(public_roles_q())


class Role(models.Model):
    NOT_STATED, OPEN, CLOSED = 'not_stated', 'open', 'closed'
    VACANCY_CHOICES = [
        (NOT_STATED, 'Not stated'),
        (OPEN, 'Currently recruiting'),
        (CLOSED, 'Not currently recruiting'),
    ]
    GENERAL, CORPORATE = 'general', 'corporate'
    TYPE_CHOICES = [
        (GENERAL, 'General position'),
        (CORPORATE, 'Corporate position'),
    ]
    FULL_TIME, PART_TIME = 'full_time', 'part_time'
    HOURS_CHOICES = [(FULL_TIME, 'Full time'), (PART_TIME, 'Part time')]
    APPLY_NONE, APPLY_FORM, APPLY_LINK, APPLY_EMAIL = 'none', 'interest_form', 'external_link', 'email'
    APPLY_CHOICES = [
        (APPLY_NONE, 'No apply button'),
        (APPLY_FORM, 'Expression-of-interest form on this page'),
        (APPLY_LINK, 'Button to an external application link'),
        (APPLY_EMAIL, 'Button that emails the application address'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='roles')
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='roles', null=True, blank=True,
        help_text='Optional. Leave empty for a company without departments: the role is listed on the company page.')
    position_type = models.CharField(
        'position type', max_length=20, choices=TYPE_CHOICES, default=GENERAL,
        help_text='General: applicants fill in a short form. Corporate: the full role details, and applicants also '
                  'upload their CV, cover letter and qualifications.')
    employment_type = models.CharField(
        'full or part time', max_length=10, choices=HOURS_CHOICES, blank=True,
        help_text='Shown on the position cards on Career Connect. Left empty, nothing is shown.')
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, help_text='Used in the web address; unique within the department '
                                                     '(or within the company, for roles without a department).')
    summary = models.CharField(max_length=300, blank=True, help_text='One line shown on the department page.')
    description = models.TextField(
        'job description', blank=True,
        help_text='Optional. Shown on the position page; leave it (and the JD file) empty to ask applicants to email HR.')
    jd_file = models.FileField(
        'job description file (JD)', upload_to='career_connect/jd/', blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx']), _jd_size],
        help_text=f'Optional. A PDF or Word file under {MAX_JD_MB} MB: applicants get a "View job description" button.')
    responsibilities = models.TextField(blank=True, help_text='One per line.')
    qualifications = models.TextField('required qualifications', blank=True, help_text='One per line.')
    skills = models.TextField('skills', blank=True, help_text='One per line.')
    vacancy_status = models.CharField(max_length=20, choices=VACANCY_CHOICES, default=NOT_STATED)
    how_to_apply = models.TextField('application instructions', blank=True,
                                    help_text='Leave blank to use the general instructions from the portal settings.')
    apply_method = models.CharField('apply button', max_length=20, choices=APPLY_CHOICES, default=APPLY_NONE)
    apply_url = models.URLField('external application link', blank=True)
    apply_email = models.EmailField('application email', blank=True)
    expires_on = models.DateField(
        'expiry date', null=True, blank=True,
        help_text='Optional. From this date the position is taken off Career Connect automatically.')
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    objects = RoleQuerySet.as_manager()

    class Meta:
        ordering = ('company__order', 'department__order', 'order', 'title')
        constraints = [
            models.UniqueConstraint(fields=('department', 'slug'), name='career_role_unique_slug'),
            models.UniqueConstraint(fields=('company', 'slug'), condition=Q(department__isnull=True),
                                    name='career_company_role_unique_slug'),
        ]
        permissions = [('manage_vacancies', 'Can post and update vacancies on the HR vacancies page')]

    def __str__(self):
        return f'{self.title} ({self.department or self.company})'

    def clean(self):
        if self.department_id and self.company_id and self.department.company_id != self.company_id:
            raise ValidationError({'department': f'Choose a department of {self.company}, or leave it empty.'})

    @property
    def place(self):
        """'Farmer Joe · Finance', or just 'Farmer Joe' for a role without a department."""
        return f'{self.company} · {self.department.name}' if self.department else str(self.company)

    def _url(self, name):
        if self.department:
            return reverse(name, args=[self.company.slug, self.department.slug, self.slug])
        return reverse(name.replace('career_connect_', 'career_connect_company_'), args=[self.company.slug, self.slug])

    def get_absolute_url(self):
        return self._url('career_connect_role')

    @property
    def interest_url(self):
        return self._url('career_connect_interest')

    @property
    def jd_url(self):
        """The public address of the uploaded job description ('' if none), with ?v= so a new upload shows."""
        if not self.jd_file:
            return ''
        return reverse('career_connect_role_jd', args=[self.pk]) + '?v=' + quote(os.path.basename(self.jd_file.name))

    @property
    def palette(self):
        return (self.department or self.company).palette

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
    def is_expired(self):
        return self.expires_on is not None and self.expires_on <= office_today()

    @property
    def is_public(self):
        """Students can see it now (the same rule as public_roles_q)."""
        return (self.is_published and not self.is_expired and self.company.is_published
                and (self.department is None or self.department.is_published))

    @property
    def recruiting_status(self):
        """What students and HR see. With an expiry date it follows the date: currently recruiting until the date is
        due, then not currently recruiting. Without one, it's the status HR chose."""
        if self.expires_on is None:
            return self.vacancy_status
        return self.CLOSED if self.is_expired else self.OPEN

    @property
    def recruiting_status_label(self):
        return dict(self.VACANCY_CHOICES)[self.recruiting_status]

    def save(self, *args, **kwargs):
        if self.department_id:   # a department's role always belongs to that department's company
            self.company_id = self.department.company_id
        if self.expires_on is not None:   # keep the stored status in step with the date
            self.vacancy_status = self.recruiting_status
        super().save(*args, **kwargs)

    @property
    def accepts_interest(self):
        return self.apply_method == self.APPLY_FORM

    @property
    def is_corporate(self):
        return self.position_type == self.CORPORATE


@deconstructible
class PrivateStorage(FileSystemStorage):
    """settings.PRIVATE_MEDIA_ROOT, read when used (so tests can point it elsewhere). It has no public address:
    the files are only handed out by the HR pages."""
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


private_storage = PrivateStorage()
ATTACHMENT_TYPES = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png']
MAX_ATTACHMENT_MB = 5


def _attachment_size(file):
    if file.size > MAX_ATTACHMENT_MB * 1024 * 1024:
        raise ValidationError(f'Each file must be smaller than {MAX_ATTACHMENT_MB} MB.')


def _attachment(label):
    return models.FileField(label, upload_to='applications/%Y/%m/', storage=private_storage, blank=True,
                            validators=[FileExtensionValidator(ATTACHMENT_TYPES), _attachment_size])


class ExpressionOfInterest(models.Model):
    """An application for a role, sent from the public form: the short form for general positions, plus the CV,
    cover letter and qualifications for corporate ones. HR read them on the vacancy's applications page."""
    ATTACHMENTS = (('cv', 'CV'), ('cover_letter', 'Cover letter'), ('qualifications_file', 'Qualifications'))
    # Where HR are with the applicant. Anything past New counts as reviewed.
    NEW, REVIEWED, INTERVIEW, OFFERED, HIRED, UNSUCCESSFUL = 'new', 'reviewed', 'interview', 'offered', 'hired', 'unsuccessful'
    STAGES = [(NEW, 'New'), (REVIEWED, 'Reviewed'), (INTERVIEW, 'Interview'), (OFFERED, 'Offered'),
              (HIRED, 'Hired'), (UNSUCCESSFUL, 'Unsuccessful')]
    INTERVIEWED = (INTERVIEW, OFFERED, HIRED)   # reached an interview (unsuccessful ones with a date did too)

    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, related_name='interests')
    role_title = models.CharField(max_length=150, help_text='Kept in case the role is later deleted.')
    full_name = models.CharField('name', max_length=120)
    age = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(14), MaxValueValidator(99)])
    village = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)   # optional: not every applicant has one
    phone = models.CharField('phone number', max_length=40, blank=True)
    highest_qualification = models.CharField('experience (highest qualification)', max_length=200, blank=True)
    cv = _attachment('CV')
    cover_letter = _attachment('cover letter')
    qualifications_file = _attachment('qualifications')
    school = models.CharField('school / institution', max_length=150, blank=True)   # earlier form
    message = models.TextField(max_length=1500, blank=True)                         # earlier form
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)
    stage = models.CharField(max_length=20, choices=STAGES, default=NEW, db_index=True)
    interview_at = models.DateTimeField('interview', null=True, blank=True)
    stage_changed_at = models.DateTimeField(null=True, blank=True, help_text='When the stage last changed, e.g. the hire date.')
    email_status = models.CharField(max_length=120, blank=True,
                                    help_text='Whether the application email reached the people in the portal settings.')

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'application'
        verbose_name_plural = 'applications'

    def save(self, *args, **kwargs):
        """Keeps `reviewed` in step with the stage, and dates each stage change (the hire date, for a hire)."""
        self.reviewed = self.stage != self.NEW
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(stage=self.stage).exists():
            self.stage_changed_at = timezone.now()
        if kwargs.get('update_fields') is not None and 'stage' in kwargs['update_fields']:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'reviewed', 'stage_changed_at'}
        super().save(*args, **kwargs)

    @property
    def stage_badge(self):
        return {self.NEW: 'badge-purple', self.REVIEWED: 'badge-gray', self.INTERVIEW: 'badge-blue',
                self.OFFERED: 'badge-amber', self.HIRED: 'badge-green', self.UNSUCCESSFUL: 'badge-red'}[self.stage]

    def attachments(self):
        """(field name, label, file) for each file this applicant uploaded."""
        return [(name, label, getattr(self, name)) for name, label in self.ATTACHMENTS if getattr(self, name)]

    def __str__(self):
        return f'{self.full_name} — {self.role_title}'


@receiver(post_delete, sender=ExpressionOfInterest)
def _delete_attachments(sender, instance, **kwargs):
    """Removing an application removes its files too."""
    for _, _, f in instance.attachments():
        f.delete(save=False)


def week_label(monday):
    """'3–9 Nov', or '27 Oct – 2 Nov' for a week that crosses into the next month."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f'{monday.day}–{sunday.day} {sunday:%b}'
    return f'{monday.day} {monday:%b} – {sunday.day} {sunday:%b}'


def turnover_rate(leavers, employees):
    """Turnover %: the employees who have left ÷ the number of employees × 100, to 2 decimal places."""
    return (Decimal(leavers) * 100 / Decimal(employees)).quantize(Decimal('0.01')) if employees else Decimal('0')


class StaffTurnover(models.Model):
    """One company's staff turnover for one week (Monday to Sunday). HR enter how many employees left that week and
    how many employees the company has; the turnover % is worked out from them (see turnover_rate). A month's
    turnover is everyone who left in its weeks ÷ the average number of employees over those weeks × 100."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='turnover')
    week = models.DateField(help_text='The Monday the week starts on. A week belongs to the month its Monday is in.')
    leavers = models.PositiveIntegerField('employees who left')
    employees = models.PositiveIntegerField('number of employees', validators=[MinValueValidator(1)])
    rate = models.DecimalField('turnover %', max_digits=6, decimal_places=2, editable=False,
                               help_text='Employees who left ÷ number of employees × 100.')
    note = models.CharField(max_length=200, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-week', 'company__order')
        constraints = [models.UniqueConstraint(fields=('company', 'week'), name='one_turnover_per_company_week')]
        verbose_name = verbose_name_plural = 'staff turnover'

    def save(self, *args, **kwargs):
        self.rate = turnover_rate(self.leavers, self.employees)
        if kwargs.get('update_fields') is not None:   # e.g. update_or_create: the % changes with the numbers
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'rate'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company}: week of {self.week:%d %b %Y} {self.rate}%'

    @property
    def week_label(self):
        return week_label(self.week)


class Employee(models.Model):
    """Someone who works (or worked) at a company in the group. HR keep the list on the Employees page (or import it
    from a CSV). Naming an employee in a week of staff turnover marks them as left, linked to that week."""
    ACTIVE, LEFT = 'active', 'left'
    STATUSES = [(ACTIVE, 'Active'), (LEFT, 'Left')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='employees')
    employee_id = models.CharField('employee ID', max_length=40, blank=True,
                                   help_text='Optional. The payroll or staff number.')
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    department = models.CharField(max_length=120, blank=True)
    position = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    start_date = models.DateField('started on', null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE)
    left_on = models.DateField('left on', null=True, blank=True)
    leaving_reason = models.CharField('reason for leaving', max_length=200, blank=True)
    turnover = models.ForeignKey(StaffTurnover, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='leavers_named', editable=False,
                                 help_text='The week of staff turnover they were counted in.')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('company__order', 'company__name', 'first_name', 'last_name')
        constraints = [models.UniqueConstraint(fields=('company', 'employee_id'), condition=~Q(employee_id=''),
                                               name='one_employee_id_per_company')]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def is_active(self):
        return self.status == self.ACTIVE

    def clean(self):
        if self.status == self.LEFT and not self.left_on:
            raise ValidationError({'left_on': 'Enter the date they left.'})

    def save(self, *args, **kwargs):
        if self.status == self.ACTIVE:   # back at work: no leaving date
            self.left_on, self.leaving_reason, self.turnover = None, '', None
        super().save(*args, **kwargs)
