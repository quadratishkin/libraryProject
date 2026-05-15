from django.urls import path

from apps.books.views import (
    BookGlossaryView,
    ConfirmRotationView,
    EditTermDefinitionView,
    ExportGlossaryView,
    ProtectBookView,
    ReanalyzeBookView,
    ResetTermDefinitionView,
    SearchView,
    StatsView,
    UploadBooksView,
    UserBookDetailView,
    UserBooksView,
)

urlpatterns = [
    path("books/", UserBooksView.as_view(), name="books-list"),
    path("books/upload/", UploadBooksView.as_view(), name="books-upload"),
    path("books/upload/confirm-rotation/", ConfirmRotationView.as_view(), name="books-upload-confirm-rotation"),
    path("books/<int:book_id>/", UserBookDetailView.as_view(), name="books-detail"),
    path("books/<int:book_id>/protect/", ProtectBookView.as_view(), name="books-protect"),
    path("books/<int:book_id>/reanalyze/", ReanalyzeBookView.as_view(), name="books-reanalyze"),
    path("books/<int:book_id>/glossary/", BookGlossaryView.as_view(), name="books-glossary"),
    path("books/<int:book_id>/terms/<int:term_id>/edit/", EditTermDefinitionView.as_view(), name="term-edit"),
    path("books/<int:book_id>/terms/<int:term_id>/reset/", ResetTermDefinitionView.as_view(), name="term-reset"),
    path("books/<int:book_id>/export/", ExportGlossaryView.as_view(), name="books-export"),
    path("search/", SearchView.as_view(), name="global-search"),
    path("stats/", StatsView.as_view(), name="stats"),
]
