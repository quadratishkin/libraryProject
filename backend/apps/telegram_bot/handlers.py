from __future__ import annotations

from io import BytesIO
from secrets import token_urlsafe

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from apps.books.models import GlobalBookCache, TermDefinition, UserBook
from apps.books.services.fb2_parser import parse_fb2
from apps.books.services.glossary_export import export_csv, export_pdf
from apps.books.services.hashing import sha256_bytes
from apps.books.services.rotation import MAX_BOOKS_PER_USER, get_user_books_count, rotate_books_if_needed
from apps.books.tasks import analyze_book_task
from apps.telegram_bot.models import TelegramProfile

router = Router()


def _book_label(book: UserBook) -> str:
    lock = "🔒 " if book.is_protected else ""
    return f"{lock}{book.title or book.original_filename} [{book.status}]"


@sync_to_async
def get_or_create_user(message: Message):
    User = get_user_model()
    telegram_id = message.from_user.id
    username = message.from_user.username or ""
    profile = TelegramProfile.objects.filter(telegram_id=telegram_id).select_related("user").first()
    if profile:
        if username and profile.username != username:
            profile.username = username
            profile.save(update_fields=["username", "updated_at"])
        return profile.user

    email = f"tg_{telegram_id}@local.local"
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"is_active": True},
    )
    if created:
        user.set_password(token_urlsafe(16))
        user.save(update_fields=["password"])
    TelegramProfile.objects.create(user=user, telegram_id=telegram_id, username=username)
    return user


@sync_to_async
def find_book_by_name(user, name: str) -> UserBook | None:
    return (
        UserBook.objects.filter(user=user, title__icontains=name)
        .select_related("global_cache")
        .order_by("-uploaded_at")
        .first()
    )


def _find_book_by_name_sync(user, name: str) -> UserBook | None:
    return (
        UserBook.objects.filter(user=user, title__icontains=name)
        .select_related("global_cache")
        .order_by("-uploaded_at")
        .first()
    )


@sync_to_async
def list_books(user):
    return list(UserBook.objects.filter(user=user).order_by("-uploaded_at")[:20])


@sync_to_async
def upload_fb2_for_user(user, filename: str, content: bytes):
    if len(content) > 50 * 1024 * 1024:
        return {"status": "error", "message": "Файл больше 50 МБ."}
    if not filename.lower().endswith(".fb2"):
        return {"status": "error", "message": "Разрешены только .fb2 файлы."}
    try:
        parse_fb2(content)
    except ValueError as exc:
        return {"status": "error", "message": f"Невалидный FB2/XML: {exc}"}

    rotation = rotate_books_if_needed(user, confirmed=True)
    if not rotation.can_upload:
        return {"status": "error", "message": rotation.reason}

    file_hash = sha256_bytes(content)
    cache = GlobalBookCache.objects.filter(file_hash=file_hash).first()
    if cache:
        user_book = UserBook.objects.create(
            user=user,
            global_cache=cache,
            title=cache.title,
            authors=cache.authors,
            original_filename=filename,
            file_hash=file_hash,
            status=UserBook.Status.READY,
        )
        return {"status": "cached", "book_id": user_book.id}

    user_book = UserBook.objects.create(
        user=user,
        original_filename=filename,
        file_hash=file_hash,
        status=UserBook.Status.PROCESSING,
    )
    user_book.file.save(filename, ContentFile(content), save=True)
    analyze_book_task.delay(user_book.id)
    return {"status": "processing", "book_id": user_book.id}


@sync_to_async
def get_book_glossary_preview(user, book_name: str):
    book = (
        UserBook.objects.filter(user=user, title__icontains=book_name, global_cache__isnull=False)
        .select_related("global_cache")
        .first()
    )
    if not book:
        return None
    terms = list(TermDefinition.objects.filter(global_cache=book.global_cache).order_by("term")[:20])
    return book, terms


@sync_to_async
def search_terms(user, query: str):
    rows = []
    books = UserBook.objects.filter(user=user, global_cache__isnull=False).select_related("global_cache")
    for book in books:
        terms = TermDefinition.objects.filter(global_cache=book.global_cache, term__icontains=query).order_by("term")[:10]
        for term in terms:
            rows.append((book, term))
    return rows[:20]


@sync_to_async
def user_stats(user):
    total = UserBook.objects.filter(user=user).count()
    protected = UserBook.objects.filter(user=user, is_protected=True).count()
    return {
        "total": total,
        "protected": protected,
        "remaining": max(0, MAX_BOOKS_PER_USER - total),
    }


@sync_to_async
def toggle_protect(user, book_name: str):
    book = _find_book_by_name_sync(user, book_name)
    if not book:
        return None
    book.is_protected = not book.is_protected
    book.save(update_fields=["is_protected"])
    return book


@sync_to_async
def export_book_pdf(user, book_name: str):
    book = _find_book_by_name_sync(user, book_name)
    if not book or not book.global_cache:
        return None
    return book, export_pdf(book), export_csv(book)


@router.message(Command("start"))
async def start_command(message: Message):
    await get_or_create_user(message)
    await message.answer("Привет! Я помогу извлечь термины и определения из FB2-книг.")


@router.message(Command("upload"))
async def upload_command(message: Message):
    await get_or_create_user(message)
    await message.answer("Отправьте FB2-файл сообщением.")


@router.message(F.document)
async def file_handler(message: Message):
    user = await get_or_create_user(message)
    document = message.document
    if not document.file_name or not document.file_name.lower().endswith(".fb2"):
        await message.answer("Ошибка: отправьте файл с расширением .fb2")
        return
    if document.file_size and document.file_size > 50 * 1024 * 1024:
        await message.answer("Ошибка: файл превышает 50 МБ.")
        return

    file = await message.bot.get_file(document.file_id)
    bio = BytesIO()
    await message.bot.download(file, destination=bio)
    result = await upload_fb2_for_user(user, document.file_name, bio.getvalue())
    if result["status"] == "processing":
        await message.answer("Книга загружена, анализ начался.")
    elif result["status"] == "cached":
        await message.answer("Книга уже есть в базе, глоссарий готов.")
    else:
        await message.answer(f"Ошибка обработки файла: {result['message']}")


@router.message(Command("my_books"))
async def my_books_command(message: Message):
    user = await get_or_create_user(message)
    books = await list_books(user)
    if not books:
        await message.answer("Книг пока нет.")
        return
    lines = ["Ваши книги:"]
    lines.extend([f"- {_book_label(book)}" for book in books])
    await message.answer("\n".join(lines))


@router.message(Command("glossary"))
async def glossary_command(message: Message, command: CommandObject):
    user = await get_or_create_user(message)
    if not command.args:
        await message.answer("Использование: /glossary <название книги>")
        return
    result = await get_book_glossary_preview(user, command.args)
    if not result:
        await message.answer("Книга не найдена.")
        return
    book, terms = result
    if not terms:
        await message.answer(f"В книге '{book.title}' терминов пока нет.")
        return
    lines = [f"Глоссарий: {book.title}", "Первые 20 терминов:"]
    for idx, term in enumerate(terms, start=1):
        lines.append(f"{idx}. {term.term}: {term.definition[:120]}")
    lines.append("Для полного списка используйте /export <название>")
    await message.answer("\n".join(lines))


@router.message(Command("search"))
async def search_command(message: Message, command: CommandObject):
    user = await get_or_create_user(message)
    if not command.args:
        await message.answer("Использование: /search <термин>")
        return
    found = await search_terms(user, command.args)
    if not found:
        await message.answer("Совпадений не найдено.")
        return
    lines = ["Результаты поиска:"]
    for book, term in found:
        lines.append(f"- {term.term} | {book.title or book.original_filename}")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def stats_command(message: Message):
    user = await get_or_create_user(message)
    stats = await user_stats(user)
    await message.answer(
        f"Книг: {stats['total']}/{MAX_BOOKS_PER_USER}\n"
        f"Защищенных: {stats['protected']}\n"
        f"Свободных мест: {stats['remaining']}"
    )


@router.message(Command("protect"))
async def protect_command(message: Message, command: CommandObject):
    user = await get_or_create_user(message)
    if not command.args:
        await message.answer("Использование: /protect <название книги>")
        return
    book = await toggle_protect(user, command.args)
    if not book:
        await message.answer("Книга не найдена.")
        return
    state = "включена" if book.is_protected else "выключена"
    await message.answer(f"Защита книги '{book.title or book.original_filename}' {state}.")


@router.message(Command("export"))
async def export_command(message: Message, command: CommandObject):
    user = await get_or_create_user(message)
    if not command.args:
        await message.answer("Использование: /export <название книги>")
        return
    payload = await export_book_pdf(user, command.args)
    if not payload:
        await message.answer("Книга не найдена или глоссарий пуст.")
        return
    book, pdf_data, csv_data = payload
    base = (book.title or f"book_{book.id}").replace(" ", "_")
    await message.answer_document(BufferedInputFile(pdf_data, filename=f"{base}.pdf"))
    await message.answer_document(BufferedInputFile(csv_data, filename=f"{base}.csv"))
