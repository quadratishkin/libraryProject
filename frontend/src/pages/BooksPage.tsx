import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BookCard from "../components/BookCard";
import Pagination from "../components/Pagination";
import UploadDropzone from "../components/UploadDropzone";
import {
  Book,
  deleteBook,
  exportGlossary,
  getBooks,
  getStats,
  reanalyzeBook,
  toggleProtectBook,
  uploadBooks
} from "../api/client";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function BooksPage() {
  const navigate = useNavigate();
  const [books, setBooks] = useState<Book[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [used, setUsed] = useState(0);
  const [limit, setLimit] = useState(50);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const loadData = async (newPage = page) => {
    setLoading(true);
    try {
      const [booksResponse, stats] = await Promise.all([getBooks(newPage), getStats()]);
      setBooks(booksResponse.results.books);
      setTotal(booksResponse.count);
      setUsed(stats.books_count);
      setLimit(stats.limit);
      setPage(newPage);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка загрузки книг");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(1);
  }, []);

  const handleUpload = async (files: File[]) => {
    setMessage("");
    const response = await uploadBooks(files, false);
    if (response.status === 201) {
      setMessage("Файлы загружены");
      await loadData(page);
      return;
    }
    if (response.status === 409 && response.data?.need_confirmation) {
      const title = response.data?.book_to_delete?.title ?? "старую книгу";
      const ok = window.confirm(`Достигнут лимит книг. Удалить ${title} и продолжить?`);
      if (!ok) return;
      const confirmed = await uploadBooks(files, true);
      if (confirmed.status === 201) {
        setMessage("Файлы загружены после ротации");
        await loadData(page);
        return;
      }
      setMessage(confirmed.data?.detail || "Ошибка загрузки");
      return;
    }
    setMessage(response.data?.detail || "Ошибка загрузки");
  };

  const handleDelete = async (bookId: number) => {
    if (!window.confirm("Удалить книгу?")) return;
    try {
      await deleteBook(bookId);
      await loadData(page);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка удаления");
    }
  };

  const handleProtect = async (bookId: number) => {
    try {
      await toggleProtectBook(bookId);
      await loadData(page);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка изменения защиты");
    }
  };

  const handleReanalyze = async (bookId: number) => {
    try {
      await reanalyzeBook(bookId);
      await loadData(page);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка запуска переанализа");
    }
  };

  const handleExport = async (bookId: number, format: "csv" | "txt" | "pdf") => {
    try {
      const file = await exportGlossary(bookId, format);
      downloadBlob(file, `book_${bookId}.${format}`);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка экспорта");
    }
  };

  return (
    <section className="container">
      <h2>Мои книги</h2>
      <p className="stats">
        {used}/{limit} книг использовано
      </p>
      <UploadDropzone onUpload={handleUpload} />
      {message && <p className="message">{message}</p>}
      {loading && <p>Загрузка...</p>}
      <div className="book-grid">
        {books.map((book) => (
          <BookCard
            key={book.id}
            book={book}
            onOpen={(id) => navigate(`/books/${id}`)}
            onProtect={handleProtect}
            onDelete={handleDelete}
            onReanalyze={handleReanalyze}
            onExport={handleExport}
          />
        ))}
      </div>
      <Pagination page={page} total={total} pageSize={20} onChange={loadData} />
    </section>
  );
}
