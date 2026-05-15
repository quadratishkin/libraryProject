import { Term } from "../api/client";

interface Props {
  term: Term;
  onEdit: (term: Term) => void;
  onReset: (term: Term) => void;
}

export default function TermCard({ term, onEdit, onReset }: Props) {
  return (
    <div className="term-card">
      <h4>{term.term}</h4>
      <p>{term.effective_definition}</p>
      {term.custom_definition && <p className="muted">Пользовательская версия</p>}
      <p className="muted">
        Источник: {term.source_chapter || "Без главы"}, абзац {term.source_paragraph_index}
      </p>
      <p className="quote">"{term.source_quote}"</p>
      <div className="card-actions">
        <button onClick={() => onEdit(term)}>Редактировать</button>
        <button onClick={() => onReset(term)}>Сбросить</button>
      </div>
    </div>
  );
}
