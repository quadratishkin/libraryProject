import { Book } from "../api/client";

interface Props {
  book: Book;
  onOpen: (bookId: number) => void;
  onProtect: (bookId: number) => void;
  onDelete: (bookId: number) => void;
  onReanalyze: (bookId: number) => void;
  onExport: (bookId: number, format: "csv" | "txt" | "pdf") => void;
}

const statusLabel: Record<Book["status"], string> = {
  uploaded: "загружено",
  processing: "анализируется",
  ready: "готово",
  failed: "ошибка"
};

export default function BookCard({ book, onOpen, onProtect, onDelete, onReanalyze, onExport }: Props) {
  return (
    <div className="book-card">
      <div className="book-header">
        <h3>{book.title || book.original_filename}</h3>
        {book.is_protected && <span title="Защищено">🔒</span>}
      </div>
      <p className="muted">{book.authors || "Автор не указан"}</p>
      <p>
        Статус: <strong>{statusLabel[book.status]}</strong>
      </p>
      {book.error_message && <p className="error-text">{book.error_message}</p>}
      <div className="card-actions">
        <button onClick={() => onOpen(book.id)}>Открыть</button>
        <button onClick={() => onProtect(book.id)}>{book.is_protected ? "Снять защиту" : "Защитить"}</button>
        <button onClick={() => onDelete(book.id)}>Удалить</button>
        <button onClick={() => onReanalyze(book.id)}>Переанализировать</button>
      </div>
      <div className="card-actions">
        <button onClick={() => onExport(book.id, "pdf")}>PDF</button>
        <button onClick={() => onExport(book.id, "txt")}>TXT</button>
        <button onClick={() => onExport(book.id, "csv")}>CSV</button>
      </div>
    </div>
  );
}
