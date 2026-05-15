import logging

from celery import shared_task
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.books.models import GlobalBookCache, TermDefinition, UserBook
from apps.books.services.fb2_parser import parse_fb2
from apps.books.services.term_extractor import extract_terms

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def analyze_book_task(self, user_book_id: int, force_reanalyze: bool = False):
    try:
        user_book = UserBook.objects.select_related("global_cache").get(id=user_book_id)
    except UserBook.DoesNotExist:
        logger.warning("UserBook %s not found for analysis", user_book_id)
        return

    try:
        user_book.status = UserBook.Status.PROCESSING
        user_book.error_message = ""
        user_book.save(update_fields=["status", "error_message"])

        content = None
        if user_book.file:
            user_book.file.open("rb")
            content = user_book.file.read()
            user_book.file.close()
        else:
            # Cached user books may not contain a local file, so we reuse a donor copy by hash.
            donor = (
                UserBook.objects.exclude(id=user_book.id)
                .exclude(file="")
                .filter(file_hash=user_book.file_hash, file__isnull=False)
                .order_by("-uploaded_at")
                .first()
            )
            if donor and donor.file:
                donor.file.open("rb")
                content = donor.file.read()
                donor.file.close()
        if not content:
            raise ValueError("File for analysis is missing")

        parsed = parse_fb2(content)
        terms = extract_terms(parsed.chapters)

        with transaction.atomic():
            cache, created = GlobalBookCache.objects.get_or_create(
                file_hash=user_book.file_hash,
                defaults={
                    "title": parsed.title,
                    "authors": parsed.authors,
                    "metadata": {"chapters_count": len(parsed.chapters), **parsed.metadata},
                },
            )

            if (created or force_reanalyze) and cache:
                TermDefinition.objects.filter(global_cache=cache).delete()
                to_create = [
                    TermDefinition(
                        global_cache=cache,
                        term=item["term"],
                        normalized_term=item["normalized_term"],
                        definition=item["definition"],
                        source_chapter=item["source_chapter"],
                        source_paragraph_index=item["source_paragraph_index"],
                        source_quote=item["source_quote"],
                        frequency=item["frequency"],
                    )
                    for item in terms
                ]
                if to_create:
                    TermDefinition.objects.bulk_create(to_create)
                cache.title = parsed.title
                cache.authors = parsed.authors
                cache.metadata = {"chapters_count": len(parsed.chapters), **parsed.metadata}
                cache.save(update_fields=["title", "authors", "metadata", "updated_at"])

        user_book.global_cache = cache
        user_book.title = cache.title
        user_book.authors = cache.authors
        user_book.status = UserBook.Status.READY
        user_book.processed_at = timezone.now()
        user_book.error_message = ""
        user_book.save(
            update_fields=[
                "global_cache",
                "title",
                "authors",
                "status",
                "processed_at",
                "error_message",
            ]
        )
    except IntegrityError:
        logger.exception("Integrity error while analyzing user_book=%s", user_book_id)
        user_book.mark_failed("Ошибка целостности данных при анализе книги.")
    except Exception as exc:
        logger.exception("Failed to analyze user_book=%s", user_book_id)
        user_book.mark_failed(str(exc))
