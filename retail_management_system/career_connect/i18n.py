"""English / Samoan for the public Career Connect pages.

English is the default. The header button sets the `cc_lang` cookie (no session: the public pages never touch it),
and every page, form label and error message is then shown in Samoan.

To change a Samoan wording, edit SAMOAN below: the key is the exact English text on the page. English text that
isn't in the table (anything typed into the admin or the HR vacancy form: role titles, descriptions, company
names...) is shown as written.
"""
from django.utils import dateformat

ENGLISH, SAMOAN_CODE = 'en', 'sm'
LANGUAGES = (ENGLISH, SAMOAN_CODE)
COOKIE = 'cc_lang'
COOKIE_AGE = 365 * 24 * 3600

MONTHS = ['Ianuari', 'Fepuari', 'Mati', 'Aperila', 'Me', 'Iuni', 'Iulai', 'Aukuso', 'Setema', 'Oketopa', 'Novema',
          'Tesema']

SAMOAN = {
    # ── Header, footer, language button ──
    'Skip to content': 'Alu sa’o i le anotusi',
    'Career Opportunities': 'Avanoa Faigaluega',
    'Ah Liki Career Connect — home': 'Ah Liki Career Connect — itulau autū',
    'Career Connect home': 'Itulau autū o Career Connect',
    # 'All rights reserved.': 'Ua puipuia aia tatau uma.',
    # 'Sending…': 'O lo’o auina atu…',
    'Read this site in Samoan': 'Faitau lenei upega tafa’ilagi i le gagana Sāmoa',
    'Read this site in English': 'Faitau lenei upega tafa’ilagi i le gagana Peretania',

    # ── Home ──
    'Now hiring': 'Avanoa Faigaluega o lo’o tausailia i le taimi nei',
    'Careers at Ah Liki': 'Galuega i Ah Liki',
    'Discover Opportunities. Build Your Future.': 'Saili Avanoa. Fausia Lou Lumana’i.',
    'Explore our departments, discover career opportunities, and learn more about Ah Liki Wholesale.':
        'Su’esu’e o matou matagaluega, maua avanoa faigaluega, ma iloa atili galuega a le Ah Liki Investment.',
    'See Open Roles': 'Va’ai i Avanoa',
    'Watch Video': 'Matamata i le Video',
    'At a glance': 'Aotelega',
    'Open position': 'Avanoa Faigaluega',
    'Open positions': 'Avanoa Faigaluega',
    'Company': 'Kamupani',
    'Companies': 'Kamupani',
    'Career path': 'Ala o galuega',
    'Career paths': 'Ala o galuega',
    'Join our team': 'Auai i la matou ’au',
    'Closes {date}': 'Tapunia i le aso {date}',
    'Apply now': 'Apalai nei loa',
    'Career opportunities': 'Avanoa Faigaluega',
    'Companies of Ah Liki Investment': 'Kamupani a Ah Liki Investment',
    'Select a company to see its departments and roles.':
        'Filifili se kamupani e va’ai i avanoa.',
    "We're hiring": 'Avanoa Faigaluega',
    '{n} position open now': '{n} avanoa faigaluega i le taimi nei',
    '{n} positions open now': '{n} avanoa faigaluega i le taimi nei',
    'Close': 'Tapuni',
    'See all open positions': 'Va’ai i avanoa faigaluega uma',
    'Maybe later': 'Mulimuli ane',
    '{n} Available Position': '{n} Avanoa Faigaluega',
    '{n} Available Positions': '{n} Avanoa Faigaluega',
    '{n} Role': '{n} Tulaga',
    '{n} Roles': '{n} Tulaga',
    '{what} — not provided yet.': '{what} — e le’i tu’uina mai.',
    'Company information': 'Fa’amatalaga o kamupani',
    'Department information': 'Fa’amatalaga o matagaluega',

    # ── Company and department pages ──
    'Departments': 'Matagaluega',
    'Roles': 'Avanoa Faigaluega',
    'No open positions at {company} right now. Please check back soon.':
        'E leai ni avanoa faigaluega i {company} i le taimi nei. Fa’amolemole toe asiasi mai.',
    'All companies': 'Kamupani uma',
    'No open roles in this department right now.': 'E leai ni avanoa faigaluega i lenei matagaluega i le taimi nei.',

    # ── Role page ──
    'Currently recruiting': 'O lo’o fa’afaigaluega',
    'Not currently recruiting': 'Ua le o fa’afaigaluega',
    'Not stated': 'E le’i ta’ua',
    'Job description': 'Fa’amatalaga o le galuega',
    'View job description': 'Va’ai i fa’amatalaga o le galuega',
    'For the full job description, please email': 'Mo fa’amatalaga atoa o le galuega, fa’amolemole imeli i le',
    'Responsibilities': 'Tiute',
    'Qualifications & skills': 'Agava’a ma tomai',
    'Required qualifications': 'Agava’a e mana’omia',
    'Skills': 'Tomai',
    'Email your application': 'Imeli lau talosaga',
    'Thank you! Your application for {role} has been sent to {company}.':
        'Fa’afetai! Ua auina atu lau talosaga mo le {role} i le {company}.',
    'Fill in your details below. Everything is needed except your email. If you have them, you can also attach your '
    'CV, cover letter and qualifications.':
        'Fa’atumu ou fa’amatalaga i lalo. E mana’omia uma vaega se’i vagana ai lau imeli. Afai e iai, e mafai fo’i ona '
        'e fa’apipi’i lau CV, tusi talosaga ma ou agava’a.',
    'Fill in your details below. Everything is needed except your email.':
        'Fa’atumu ou fa’amatalaga i lalo. E mana’omia uma vaega se’i vagana ai lau imeli.',
    'Attachments': 'Faila e fa’apipi’i',
    'Submit application': 'Auina atu le talosaga',

    # ── Application form ──
    'Name': 'Igoa',
    'Age': 'Tausaga',
    'Village': 'Nu’u/Alalafaga',
    'Email': 'Imeli',
    'Email (optional)': 'Imeli (pe afai e iai)',
    'Phone number': 'Numera o le telefoni',
    'Experience (highest qualification)': 'Tusi pasi maualuga (agava’a maualuga)',
    'e.g. Year 13 certificate, or 2 years in retail':
        'fa’ata’ita’iga: Tusi pasi o le Tausaga 13, po’o le 2 tausaga i le fa’atauoloa',
    'I agree that Ah Liki may contact me about this position using the details above.':
        'Ou te malie e mafai e Ah Liki ona fa’afeso’ota’i a’u e uiga i lenei avanoa faigaluega, e fa’aaoga ai fa’amatalaga '
        'o lo’o i luga.',
    'CV (optional)': 'CV (pe afai e iai)',
    'Cover letter (optional)': 'Tusi talosaga (pe afai e iai)',
    'Qualifications (optional)': 'Agava’a (pe afai e iai)',
    'PDF, Word or a photo, under {mb} MB.': 'PDF, Word po’o se ata, e la’ititi ifo i le {mb} MB.',
    'Certificates or transcripts in one file. PDF, Word or a photo, under {mb} MB.':
        'Tusi pasi po’o fa’amaumauga o togi i se faila e tasi. PDF, Word po’o se ata, e la’ititi '
        'ifo i le {mb} MB.',

    # ── Form errors ──
    'This field is required.': 'E mana’omia lenei vaega.',
    'Enter a valid email address.': 'Tusi mai se tuatusi imeli sa’o.',
    'Enter a whole number.': 'Tusi mai se numera atoa.',
    'Ensure this value is greater than or equal to {n}.': 'Ia le itiiti ifo i le {n}.',
    'Ensure this value is less than or equal to {n}.': 'Ia le sili atu i le {n}.',
    'Each file must be smaller than {mb} MB.': 'E tatau ona la’ititi ifo faila ta’itasi i le {mb} MB.',
    'That type of file is not allowed. Use PDF, Word or a photo (JPG or PNG).':
        'E le fa’atagaina lea ituaiga faila. Fa’aaoga le PDF, Word po’o se ata (JPG po’o PNG).',
    'The submitted file is empty.': 'O le faila na auina mai e leai se mea i totonu.',
    'Too many submissions from your network. Please try again in an hour.':
        'Ua tele naua talosaga mai lau feso’ota’iga. Fa’amolemole toe taumafai i se itula.',

    # ── Portal switched off ──
    'Career Connect is not available right now': 'E le o avanoa Career Connect i le taimi nei',
    'Please check back soon.': 'Fa’amolemole toe asiasi mai.',
}


def get_language(request):
    lang = request.COOKIES.get(COOKIE)
    return lang if lang in LANGUAGES else ENGLISH


def translate(text, lang, **values):
    """`text` in `lang` (unchanged when it's English or not in the table), with {placeholders} filled in."""
    text = '' if text is None else str(text)
    if lang == SAMOAN_CODE:
        text = SAMOAN.get(text, text)
    return text.format(**values) if values else text


def plural(n, singular, plural_text, lang, **values):
    return translate(singular if n == 1 else plural_text, lang, n=n, **values)


def format_date(value, fmt, lang):
    """Django date format, with Samoan month names (in full: Samoan has no short forms) when lang is Samoan."""
    if not value:
        return ''
    if lang != SAMOAN_CODE:
        return dateformat.format(value, fmt)
    out = []
    for ch in fmt:
        if ch in 'MF':
            out.append(MONTHS[value.month - 1])
        elif ch in 'jdYy':
            out.append(dateformat.format(value, ch))
        else:
            out.append(ch)
    return ''.join(out)


# Django's own form messages come with the numbers filled in; these turn them back into table keys
_PATTERNS = (
    ('Ensure this value is greater than or equal to ', 'Ensure this value is greater than or equal to {n}.'),
    ('Ensure this value is less than or equal to ', 'Ensure this value is less than or equal to {n}.'),
)


def translate_error(message, lang):
    if lang != SAMOAN_CODE:
        return message
    message = str(message)
    if message in SAMOAN:
        return SAMOAN[message]
    if message.startswith('File extension'):
        return SAMOAN['That type of file is not allowed. Use PDF, Word or a photo (JPG or PNG).']
    if message.startswith('Each file must be smaller than'):
        return translate('Each file must be smaller than {mb} MB.', lang, mb=message.split('than ')[1].split(' ')[0])
    for prefix, key in _PATTERNS:
        if message.startswith(prefix):
            return translate(key, lang, n=message[len(prefix):].rstrip('.'))
    return message
