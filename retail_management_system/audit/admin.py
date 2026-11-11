from django.contrib import admin
from django.utils.html import format_html, format_html_join

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """Read-only: the log can be searched and filtered, never edited or emptied."""
    list_display = ('at', 'username', 'action_badge', 'model_name', 'object_repr', 'summary')
    list_filter = ('action', 'content_type', 'username', 'at')
    search_fields = ('username', 'object_repr', 'object_id', 'path')
    date_hierarchy = 'at'
    list_per_page = 50
    fields = ('at', 'username', 'action', 'model_name', 'object_repr', 'object_id', 'change_table', 'path', 'ip')
    readonly_fields = fields
    list_select_related = ('content_type',)

    @admin.display(description='Action', ordering='action')
    def action_badge(self, obj):
        colour = {'added': '#15803D', 'changed': '#1D4ED8', 'deleted': '#B91C1C'}.get(obj.action, '#475569')
        return format_html('<b style="color:{}">{}</b>', colour, obj.get_action_display())

    @admin.display(description='What')
    def model_name(self, obj):
        return obj.model_name

    @admin.display(description='Fields')
    def summary(self, obj):
        names = list(obj.changes)
        return ', '.join(names[:5]) + (f' +{len(names) - 5} more' if len(names) > 5 else '')

    @admin.display(description='Changes')
    def change_table(self, obj):
        if not obj.changes:
            return '—'
        rows = format_html_join('', '<tr><th style="text-align:left;padding:4px 12px 4px 0">{}</th>'
                                    '<td style="padding:4px 12px;color:#B91C1C">{}</td>'
                                    '<td style="padding:4px 12px;color:#15803D">{}</td></tr>',
                                ((k, '' if v[0] is None else v[0], '' if v[1] is None else v[1])
                                 for k, v in obj.changes.items()))
        return format_html('<table><tr><th style="text-align:left">Field</th><th style="padding:0 12px">Before</th>'
                           '<th style="padding:0 12px">After</th></tr>{}</table>', rows)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
