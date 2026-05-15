from django.conf import settings
from django.db import models
from django.utils import timezone


class GlobalBookCache(models.Model):
    file_hash = models.CharField(max_length=64, unique=True, db_index=True)
    title = models.CharField(max_length=512)
    authors = models.CharField(max_length=512, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.title} ({self.file_hash[:12]})"


class UserBook(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="books")
    global_cache = models.ForeignKey(
        GlobalBookCache,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_books",
    )
    title = models.CharField(max_length=512, blank=True)
    authors = models.CharField(max_length=512, blank=True)
    original_filename = models.CharField(max_length=512)
    file_hash = models.CharField(max_length=64, db_index=True)
    file = models.FileField(upload_to="books/%Y/%m/%d/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    error_message = models.TextField(blank=True)
    is_protected = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-uploaded_at",)
        indexes = [
            models.Index(fields=("user", "uploaded_at")),
            models.Index(fields=("user", "status")),
        ]

    def mark_failed(self, message: str):
        self.status = UserBook.Status.FAILED
        self.error_message = message[:2000]
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "processed_at"])

    def __str__(self):
        return f"{self.user_id}: {self.title or self.original_filename}"


class TermDefinition(models.Model):
    global_cache = models.ForeignKey(GlobalBookCache, on_delete=models.CASCADE, related_name="terms")
    term = models.CharField(max_length=255)
    normalized_term = models.CharField(max_length=255, db_index=True)
    definition = models.TextField()
    source_chapter = models.CharField(max_length=255, blank=True)
    source_paragraph_index = models.PositiveIntegerField(default=0)
    source_quote = models.TextField(blank=True)
    frequency = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("term",)
        unique_together = ("global_cache", "normalized_term")
        indexes = [
            models.Index(fields=("global_cache", "term")),
            models.Index(fields=("global_cache", "normalized_term")),
        ]

    def __str__(self):
        return self.term


class UserTermEdit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="term_edits")
    user_book = models.ForeignKey(UserBook, on_delete=models.CASCADE, related_name="term_edits")
    term_definition = models.ForeignKey(TermDefinition, on_delete=models.CASCADE, related_name="user_edits")
    custom_definition = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user_book", "term_definition")

    def __str__(self):
        return f"{self.user_id}:{self.term_definition.term}"
