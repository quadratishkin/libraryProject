from __future__ import annotations

import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import pagination, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.books.models import GlobalBookCache, TermDefinition, UserBook, UserTermEdit
from apps.books.serializers import (
    TermDefinitionSerializer,
    UserBookDetailSerializer,
    UserBookSerializer,
    UserTermEditSerializer,
)
from apps.books.services.fb2_parser import parse_fb2
from apps.books.services.glossary_export import export_csv, export_pdf, export_txt
from apps.books.services.hashing import sha256_bytes
from apps.books.services.rotation import (
    MAX_BOOKS_PER_USER,
    get_oldest_unprotected_book,
    get_user_books_count,
    rotate_books_if_needed,
)
from apps.books.services.term_extractor import normalize_term
from apps.books.tasks import analyze_book_task


class BookPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class GlossaryPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _bool_from_request(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _book_to_delete_payload(book: UserBook | None):
    if not book:
        return None
    return {
        "id": book.id,
        "title": book.title or book.original_filename,
        "uploaded_at": book.uploaded_at,
        "is_protected": book.is_protected,
    }


class UserBooksView(APIView):
    def get(self, request):
        queryset = UserBook.objects.filter(user=request.user).order_by("-uploaded_at")
        paginator = BookPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = UserBookSerializer(page, many=True)
        return paginator.get_paginated_response(
            {
                "books": serializer.data,
                "books_used": get_user_books_count(request.user),
                "books_limit": MAX_BOOKS_PER_USER,
            }
        )


class UploadBooksView(APIView):
    def post(self, request):
        files = request.FILES.getlist("files")
        if not files and "file" in request.FILES:
            files = [request.FILES["file"]]
        if not files:
            return Response({"detail": "Файлы не переданы."}, status=status.HTTP_400_BAD_REQUEST)

        confirm_rotation = _bool_from_request(request.data.get("confirm_rotation"))
        current_count = get_user_books_count(request.user)
        # Multi-upload asks for explicit confirmation before automatic deletion.
        if current_count + len(files) > MAX_BOOKS_PER_USER and not confirm_rotation:
            candidate = get_oldest_unprotected_book(request.user)
            if not candidate:
                return Response(
                    {"detail": "Достигнут лимит 50 книг, и все книги защищены."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "need_confirmation": True,
                    "book_to_delete": _book_to_delete_payload(candidate),
                    "detail": "Нужно подтверждение ротации книг.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        created_items = []
        for uploaded_file in files:
            if uploaded_file.size > settings.MAX_FB2_FILE_SIZE:
                return Response(
                    {"detail": f"Файл {uploaded_file.name} превышает лимит 50 МБ."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not uploaded_file.name.lower().endswith(".fb2"):
                return Response(
                    {"detail": f"Файл {uploaded_file.name} не является FB2."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if get_user_books_count(request.user) >= MAX_BOOKS_PER_USER:
                rotation = rotate_books_if_needed(request.user, confirmed=confirm_rotation)
                if not rotation.can_upload:
                    return Response(
                        {
                            "need_confirmation": rotation.need_confirmation,
                            "book_to_delete": _book_to_delete_payload(rotation.book_to_delete),
                            "detail": rotation.reason,
                        },
                        status=status.HTTP_409_CONFLICT if rotation.need_confirmation else status.HTTP_400_BAD_REQUEST,
                    )

            content = uploaded_file.read()
            if not content:
                return Response({"detail": f"Файл {uploaded_file.name} пустой."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                parse_fb2(content)
            except ValueError as exc:
                return Response(
                    {"detail": f"Файл {uploaded_file.name} содержит невалидный XML: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            file_hash = sha256_bytes(content)
            global_cache = GlobalBookCache.objects.filter(file_hash=file_hash).first()
            original_filename = os.path.basename(uploaded_file.name)

            if global_cache:
                user_book = UserBook.objects.create(
                    user=request.user,
                    global_cache=global_cache,
                    title=global_cache.title,
                    authors=global_cache.authors,
                    original_filename=original_filename,
                    file_hash=file_hash,
                    status=UserBook.Status.READY,
                )
                created_items.append({"id": user_book.id, "status": user_book.status, "used_cache": True})
                continue

            user_book = UserBook.objects.create(
                user=request.user,
                original_filename=original_filename,
                file_hash=file_hash,
                status=UserBook.Status.PROCESSING,
            )
            user_book.file.save(original_filename, ContentFile(content), save=True)
            analyze_book_task.delay(user_book.id)
            created_items.append({"id": user_book.id, "status": user_book.status, "used_cache": False})

        return Response({"results": created_items}, status=status.HTTP_201_CREATED)


class ConfirmRotationView(APIView):
    def post(self, request):
        rotation = rotate_books_if_needed(request.user, confirmed=True)
        if not rotation.can_upload:
            return Response(
                {
                    "detail": rotation.reason,
                    "need_confirmation": rotation.need_confirmation,
                    "book_to_delete": _book_to_delete_payload(rotation.book_to_delete),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": rotation.reason or "Ротация выполнена."})


class UserBookDetailView(APIView):
    def get_object(self, user, book_id) -> UserBook:
        return get_object_or_404(UserBook, id=book_id, user=user)

    def get(self, request, book_id):
        user_book = self.get_object(request.user, book_id)
        return Response(UserBookDetailSerializer(user_book).data)

    def delete(self, request, book_id):
        user_book = self.get_object(request.user, book_id)
        if user_book.is_protected:
            return Response(
                {"detail": "Сначала снимите защиту с книги."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user_book.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProtectBookView(APIView):
    def post(self, request, book_id):
        user_book = get_object_or_404(UserBook, id=book_id, user=request.user)
        user_book.is_protected = not user_book.is_protected
        user_book.save(update_fields=["is_protected"])
        return Response({"id": user_book.id, "is_protected": user_book.is_protected})


class ReanalyzeBookView(APIView):
    def post(self, request, book_id):
        user_book = get_object_or_404(UserBook, id=book_id, user=request.user)
        user_book.status = UserBook.Status.PROCESSING
        user_book.error_message = ""
        user_book.save(update_fields=["status", "error_message"])
        analyze_book_task.delay(user_book.id, force_reanalyze=True)
        return Response({"detail": "Переанализ запущен.", "status": user_book.status})


class BookGlossaryView(APIView):
    def get(self, request, book_id):
        user_book = get_object_or_404(UserBook.objects.select_related("global_cache"), id=book_id, user=request.user)
        if not user_book.global_cache:
            return Response({"results": [], "count": 0})

        UserBook.objects.filter(id=user_book.id).update(views_count=F("views_count") + 1)
        user_book.refresh_from_db(fields=["views_count"])

        terms = TermDefinition.objects.filter(global_cache=user_book.global_cache).order_by("term")
        q = request.query_params.get("q", "").strip()
        chapter = request.query_params.get("chapter", "").strip()
        if q:
            q_normalized = normalize_term(q)
            terms = terms.filter(
                Q(term__icontains=q)
                | Q(normalized_term__icontains=q_normalized)
                | Q(definition__icontains=q)
                | Q(source_quote__icontains=q)
            )
        if chapter:
            terms = terms.filter(source_chapter__icontains=chapter)

        edits = {
            edit.term_definition_id: edit
            for edit in UserTermEdit.objects.filter(user=request.user, user_book=user_book)
        }
        paginator = GlossaryPagination()
        page = paginator.paginate_queryset(terms, request)
        serializer = TermDefinitionSerializer(page, many=True, context={"edits_map": edits})
        return paginator.get_paginated_response({"book_id": user_book.id, "views_count": user_book.views_count, "terms": serializer.data})


class EditTermDefinitionView(APIView):
    def patch(self, request, book_id, term_id):
        user_book = get_object_or_404(UserBook.objects.select_related("global_cache"), id=book_id, user=request.user)
        if not user_book.global_cache:
            return Response({"detail": "У книги отсутствует глоссарий."}, status=status.HTTP_400_BAD_REQUEST)

        term = get_object_or_404(TermDefinition, id=term_id, global_cache=user_book.global_cache)
        serializer = UserTermEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edit, _ = UserTermEdit.objects.update_or_create(
            user=request.user,
            user_book=user_book,
            term_definition=term,
            defaults={"custom_definition": serializer.validated_data["custom_definition"]},
        )
        term_serializer = TermDefinitionSerializer(
            term,
            context={"edits_map": {term.id: edit}},
        )
        return Response(term_serializer.data)


class ResetTermDefinitionView(APIView):
    def post(self, request, book_id, term_id):
        user_book = get_object_or_404(UserBook.objects.select_related("global_cache"), id=book_id, user=request.user)
        if not user_book.global_cache:
            return Response({"detail": "У книги отсутствует глоссарий."}, status=status.HTTP_400_BAD_REQUEST)
        term = get_object_or_404(TermDefinition, id=term_id, global_cache=user_book.global_cache)
        UserTermEdit.objects.filter(user=request.user, user_book=user_book, term_definition=term).delete()
        return Response(TermDefinitionSerializer(term, context={"edits_map": {}}).data)


class SearchView(APIView):
    pagination_class = GlossaryPagination

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"count": 0, "results": []})
        normalized_q = normalize_term(q)

        user_books = (
            UserBook.objects.select_related("global_cache")
            .filter(user=request.user, global_cache__isnull=False, status=UserBook.Status.READY)
            .order_by("-uploaded_at")
        )
        results = []
        for user_book in user_books:
            terms = TermDefinition.objects.filter(global_cache=user_book.global_cache).filter(
                Q(term__icontains=q) | Q(normalized_term__icontains=normalized_q) | Q(definition__icontains=q)
            )
            edits = {
                edit.term_definition_id: edit.custom_definition
                for edit in UserTermEdit.objects.filter(user=request.user, user_book=user_book)
            }
            for term in terms:
                results.append(
                    {
                        "book_id": user_book.id,
                        "book_title": user_book.title or user_book.original_filename,
                        "term_id": term.id,
                        "term": term.term,
                        "definition": edits.get(term.id, term.definition),
                        "context": term.source_quote,
                        "chapter": term.source_chapter,
                    }
                )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(page)


class StatsView(APIView):
    def get(self, request):
        total = UserBook.objects.filter(user=request.user).count()
        protected_count = UserBook.objects.filter(user=request.user, is_protected=True).count()
        return Response(
            {
                "books_count": total,
                "protected_books_count": protected_count,
                "limit": MAX_BOOKS_PER_USER,
                "remaining_slots": max(0, MAX_BOOKS_PER_USER - total),
            }
        )


class ExportGlossaryView(APIView):
    def get(self, request, book_id):
        user_book = get_object_or_404(UserBook.objects.select_related("global_cache"), id=book_id, user=request.user)
        if not user_book.global_cache or user_book.global_cache.terms.count() == 0:
            return Response({"detail": "Глоссарий пуст."}, status=status.HTTP_400_BAD_REQUEST)

        export_format = request.query_params.get("format", "csv").lower()
        if export_format == "csv":
            content = export_csv(user_book)
            content_type = "text/csv; charset=utf-8"
            ext = "csv"
        elif export_format == "txt":
            content = export_txt(user_book)
            content_type = "text/plain; charset=utf-8"
            ext = "txt"
        elif export_format == "pdf":
            content = export_pdf(user_book)
            content_type = "application/pdf"
            ext = "pdf"
        else:
            return Response({"detail": "Поддерживаются только csv/txt/pdf."}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(content, content_type=content_type)
        filename = f"glossary_book_{user_book.id}.{ext}"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
