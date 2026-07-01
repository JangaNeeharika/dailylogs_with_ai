from django.contrib import admin
from .models import Profile, Log, Mark
from .models import ChatMessage

admin.site.register(ChatMessage)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'role', 'college', 'color')
    list_filter   = ('role',)
    search_fields = ('user__username', 'college')


class MarkInline(admin.StackedInline):
    model  = Mark
    extra  = 0
    fields = ('mentor', 'stars', 'note', 'marked_at')
    readonly_fields = ('marked_at',)


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display  = ('member', 'date', 'title', 'hours_spent', 'has_mark', 'created_at')
    list_filter   = ('date', 'member__profile__role')
    search_fields = ('member__username', 'title', 'tags')
    ordering      = ('-date', '-created_at')
    inlines       = [MarkInline]
    readonly_fields = ('created_at',)

    def has_mark(self, obj):
        return hasattr(obj, 'mark')
    has_mark.boolean = True
    has_mark.short_description = 'Marked?'


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display  = ('log', 'mentor', 'stars', 'note', 'marked_at')
    list_filter   = ('stars', 'mentor')
    search_fields = ('log__title', 'mentor__username', 'note')
    readonly_fields = ('marked_at',)