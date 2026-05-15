import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, setAuthToken } from "../api/client";

interface Props {
  onSuccess: () => void;
}

export default function LoginPage({ onSuccess }: Props) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const response = await login(email, password);
      setAuthToken(response.token);
      onSuccess();
      navigate("/books");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Ошибка входа");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="auth-card">
      <h2>Вход</h2>
      <form onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input
          type="password"
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit" disabled={isLoading}>
          {isLoading ? "Входим..." : "Войти"}
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
      <p>
        Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
      </p>
    </section>
  );
}
