from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.books.models import GlobalBookCache, TermDefinition, UserBook
from apps.books.services.hashing import sha256_bytes
from apps.books.services.term_extractor import extract_terms

VALID_FB2 = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description>
    <title-info>
      <book-title>Python Basics</book-title>
      <author><first-name>Ivan</first-name><last-name>Petrov</last-name></author>
    </title-info>
  </description>
  <body>
    <section>
      <title><p>Глава 1</p></title>
      <p>Инкапсуляция — это механизм объединения данных и методов.</p>
      <p>Класс представляет собой шаблон для создания объектов.</p>
    </section>
  </body>
</FictionBook>
""".encode("utf-8")


class BooksApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="booker@example.com", password="StrongPass123")
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _upload(self, name="book.fb2", content=VALID_FB2, extra_data=None):
        data = {"files": [SimpleUploadedFile(name, content, content_type="application/xml")]}
        if extra_data:
            data.update(extra_data)
        return self.client.post("/api/books/upload/", data, format="multipart")

    def test_upload_valid_fb2(self):
        with patch("apps.books.views.analyze_book_task.delay"):
            response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserBook.objects.count(), 1)

    def test_reject_non_fb2_upload(self):
        response = self._upload(name="book.txt")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(MAX_FB2_FILE_SIZE=10)
    def test_reject_too_large_file(self):
        large_content = b"x" * 20
        response = self._upload(content=large_content)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sha256_hash(self):
        digest = sha256_bytes(VALID_FB2)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, sha256_bytes(VALID_FB2))

    def test_reupload_uses_global_cache(self):
        file_hash = sha256_bytes(VALID_FB2)
        cache = GlobalBookCache.objects.create(
            file_hash=file_hash,
            title="Cached title",
            authors="Cached author",
            metadata={"chapters_count": 1},
        )
        response = self._upload(content=VALID_FB2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        book = UserBook.objects.get()
        self.assertEqual(book.status, UserBook.Status.READY)
        self.assertEqual(book.global_cache, cache)

    def test_term_extraction_rule(self):
        chapters = [{"chapter_title": "Глава 1", "paragraphs": ["Инкапсуляция — это механизм объединения данных."]}]
        terms = extract_terms(chapters)
        self.assertTrue(any(item["term"].lower() == "инкапсуляция" for item in terms))

    def test_global_search(self):
        cache = GlobalBookCache.objects.create(
            file_hash="a" * 64,
            title="Book 1",
            authors="Author",
            metadata={},
        )
        book = UserBook.objects.create(
            user=self.user,
            global_cache=cache,
            title="Book 1",
            authors="Author",
            original_filename="book.fb2",
            file_hash="a" * 64,
            status=UserBook.Status.READY,
        )
        TermDefinition.objects.create(
            global_cache=cache,
            term="Инкапсуляция",
            normalized_term="инкапсуляция",
            definition="Инкапсуляция — это механизм...",
            source_chapter="Глава 1",
            source_paragraph_index=1,
            source_quote="Инкапсуляция — это механизм...",
            frequency=2,
        )
        response = self.client.get("/api/search/?q=инкапсуляция")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["count"] >= 1)
        self.assertEqual(response.data["results"][0]["book_id"], book.id)

    def test_protect_toggle(self):
        book = UserBook.objects.create(
            user=self.user,
            original_filename="book.fb2",
            file_hash="b" * 64,
            status=UserBook.Status.UPLOADED,
        )
        response = self.client.post(f"/api/books/{book.id}/protect/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        book.refresh_from_db()
        self.assertTrue(book.is_protected)

    def test_delete_unprotected_book(self):
        book = UserBook.objects.create(
            user=self.user,
            original_filename="book.fb2",
            file_hash="c" * 64,
            status=UserBook.Status.UPLOADED,
        )
        response = self.client.delete(f"/api/books/{book.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UserBook.objects.filter(id=book.id).exists())

    def test_delete_protected_book_forbidden(self):
        book = UserBook.objects.create(
            user=self.user,
            original_filename="book.fb2",
            file_hash="d" * 64,
            status=UserBook.Status.UPLOADED,
            is_protected=True,
        )
        response = self.client.delete(f"/api/books/{book.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(UserBook.objects.filter(id=book.id).exists())

    def test_rotation_when_uploading_51st_book(self):
        cache = GlobalBookCache.objects.create(
            file_hash=sha256_bytes(VALID_FB2),
            title="Cached",
            authors="Author",
            metadata={},
        )
        for index in range(50):
            UserBook.objects.create(
                user=self.user,
                global_cache=cache,
                title=f"Book {index}",
                authors="Author",
                original_filename=f"book_{index}.fb2",
                file_hash=f"{index:064d}"[-64:],
                status=UserBook.Status.READY,
                is_protected=index > 0,
            )
        response = self._upload(content=VALID_FB2)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(response.data["need_confirmation"])

        response_confirmed = self._upload(content=VALID_FB2, extra_data={"confirm_rotation": "true"})
        self.assertEqual(response_confirmed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserBook.objects.filter(user=self.user).count(), 50)
