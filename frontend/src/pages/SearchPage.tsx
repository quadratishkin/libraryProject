import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import Pagination from "../components/Pagination";
import { SearchResult, globalSearch } from "../api/client";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");

  const executeSearch = async (nextPage = 1) => {
    if (!query.trim()) return;
    try {
      const response = await globalSearch(query, nextPage);
      setResults(response.results);
      setTotal(response.count);
      setPage(nextPage);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Ошибка поиска");
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await executeSearch(1);
  };

  return (
    <section className="container">
      <h2>Глобальный поиск</h2>
      <form className="search-form" onSubmit={onSubmit}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Введите термин" />
        <button type="submit">Найти</button>
      </form>
      {error && <p className="error-text">{error}</p>}
      <div className="search-results">
        {results.map((item) => (
          <article key={`${item.book_id}-${item.term_id}`} className="search-card">
            <h4>{item.term}</h4>
            <p>{item.definition}</p>
            <p className="muted">Книга: {item.book_title}</p>
            <p className="quote">Контекст: {item.context}</p>
            <Link to={`/books/${item.book_id}`}>Перейти к книге</Link>
          </article>
        ))}
      </div>
      <Pagination page={page} total={total} pageSize={50} onChange={executeSearch} />
    </section>
  );
}
