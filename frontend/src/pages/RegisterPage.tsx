import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register, setAuthToken } from "../api/client";

interface Props {
  onSuccess: () => void;
}

export default function RegisterPage({ onSuccess }: Props) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordRepeat, setPasswordRepeat] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (password !== passwordRepeat) {
      setError("Пароли не совпадают");
      return;
    }
    setIsLoading(true);
    try {
      const response = await register(email, password, passwordRepeat);
      setAuthToken(response.token);
      onSuccess();
      navigate("/books");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Ошибка регистрации");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="auth-card">
      <h2>Регистрация</h2>
      <form onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input
          type="password"
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Повторите пароль"
          value={passwordRepeat}
          onChange={(e) => setPasswordRepeat(e.target.value)}
          required
        />
        <button type="submit" disabled={isLoading}>
          {isLoading ? "Создаем..." : "Зарегистрироваться"}
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
      <p>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </p>
    </section>
  );
}
