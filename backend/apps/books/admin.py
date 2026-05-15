from django.contrib import admin

from .models import GlobalBookCache, TermDefinition, UserBook, UserTermEdit


@admin.register(GlobalBookCache)
class GlobalBookCacheAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "file_hash", "updated_at")
    search_fields = ("title", "authors", "file_hash")


@admin.register(UserBook)
class UserBookAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "status", "is_protected", "uploaded_at")
    list_filter = ("status", "is_protected")
    search_fields = ("title", "authors", "file_hash", "original_filename")


@admin.register(TermDefinition)
class TermDefinitionAdmin(admin.ModelAdmin):
    list_display = ("id", "term", "global_cache", "frequency")
    search_fields = ("term", "normalized_term")


@admin.register(UserTermEdit)
class UserTermEditAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "user_book", "term_definition", "updated_at")
