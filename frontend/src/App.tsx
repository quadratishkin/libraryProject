import { useMemo, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { getAuthToken, logout, setAuthToken } from "./api/client";
import BookGlossaryPage from "./pages/BookGlossaryPage";
import BooksPage from "./pages/BooksPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import SearchPage from "./pages/SearchPage";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const token = getAuthToken();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function Navigation({ onLogout }: { onLogout: () => void }) {
  return (
    <header className="top-nav">
      <h1>Интеллектуальная библиотека</h1>
      <nav>
        <Link to="/books">Книги</Link>
        <Link to="/search">Поиск</Link>
        <button onClick={onLogout}>Выйти</button>
      </nav>
    </header>
  );
}

function AppContent() {
  const navigate = useNavigate();
  const [authTick, setAuthTick] = useState(0);
  const isAuthenticated = useMemo(() => !!getAuthToken(), [authTick]);

  const handleAuthSuccess = () => setAuthTick((value) => value + 1);

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setAuthToken(null);
      setAuthTick((value) => value + 1);
      navigate("/login");
    }
  };

  return (
    <div className="app-shell">
      {isAuthenticated && <Navigation onLogout={handleLogout} />}
      <main>
        <Routes>
          <Route path="/login" element={<LoginPage onSuccess={handleAuthSuccess} />} />
          <Route path="/register" element={<RegisterPage onSuccess={handleAuthSuccess} />} />
          <Route
            path="/books"
            element={
              <ProtectedRoute>
                <BooksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/books/:id"
            element={
              <ProtectedRoute>
                <BookGlossaryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/search"
            element={
              <ProtectedRoute>
                <SearchPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to={isAuthenticated ? "/books" : "/login"} replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
