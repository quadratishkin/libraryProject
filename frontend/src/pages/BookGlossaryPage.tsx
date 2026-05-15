import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Pagination from "../components/Pagination";
import TermCard from "../components/TermCard";
import { Term, editTerm, getBook, getGlossary, resetTerm } from "../api/client";

export default function BookGlossaryPage() {
  const { id } = useParams();
  const bookId = Number(id);
  const [bookTitle, setBookTitle] = useState("");
  const [terms, setTerms] = useState<Term[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [chapter, setChapter] = useState("");
  const [message, setMessage] = useState("");

  const load = async (nextPage = page, nextQuery = query, nextChapter = chapter) => {
    try {
      const [book, glossary] = await Promise.all([getBook(bookId), getGlossary(bookId, nextPage, nextQuery, nextChapter)]);
      setBookTitle(book.title || book.original_filename);
      setTerms(glossary.results.terms);
      setTotal(glossary.count);
      setPage(nextPage);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Ошибка загрузки глоссария");
    }
  };

  useEffect(() => {
    load(1, "", "");
  }, [bookId]);

  const chapterOptions = useMemo(
    () => Array.from(new Set(terms.map((term) => term.source_chapter).filter(Boolean))),
    [terms]
  );

  const handleEdit = async (term: Term) => {
    const value = window.prompt("Введите пользовательское определение", term.effective_definition);
    if (!value) return;
    await editTerm(bookId, term.id, value);
    await load(page, query, chapter);
  };

  const handleReset = async (term: Term) => {
    await resetTerm(bookId, term.id);
    await load(page, query, chapter);
  };

  return (
    <section className="container">
      <div className="inline-row">
        <Link to="/books">← Назад к книгам</Link>
      </div>
      <h2>{bookTitle}</h2>
      <div className="filters">
        <input
          type="text"
          placeholder="Поиск по терминам"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={chapter} onChange={(e) => setChapter(e.target.value)}>
          <option value="">Все главы</option>
          {chapterOptions.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <button onClick={() => load(1, query, chapter)}>Искать</button>
      </div>
      {message && <p className="error-text">{message}</p>}
      <div className="term-list">
        {terms.map((term) => (
          <TermCard key={term.id} term={term} onEdit={handleEdit} onReset={handleReset} />
        ))}
      </div>
      <Pagination page={page} total={total} pageSize={50} onChange={(p) => load(p, query, chapter)} />
    </section>
  );
}
