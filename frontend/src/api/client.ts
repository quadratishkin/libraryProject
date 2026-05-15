import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";
const TOKEN_KEY = "smart_library_token";

export type BookStatus = "uploaded" | "processing" | "ready" | "failed";

export interface Book {
  id: number;
  title: string;
  authors: string;
  original_filename: string;
  file_hash: string;
  status: BookStatus;
  error_message: string;
  is_protected: boolean;
  views_count: number;
  uploaded_at: string;
  processed_at: string | null;
  terms_count?: number;
}

export interface Term {
  id: number;
  term: string;
  normalized_term: string;
  definition: string;
  effective_definition: string;
  custom_definition?: string | null;
  source_chapter: string;
  source_paragraph_index: number;
  source_quote: string;
  frequency: number;
}

export interface SearchResult {
  book_id: number;
  book_title: string;
  term_id: number;
  term: string;
  definition: string;
  context: string;
  chapter: string;
}

const client = axios.create({
  baseURL: API_URL
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  return config;
});

export function setAuthToken(token: string | null) {
  if (!token) {
    localStorage.removeItem(TOKEN_KEY);
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export async function register(email: string, password: string, passwordRepeat: string) {
  const response = await client.post("/auth/register/", {
    email,
    password,
    password_repeat: passwordRepeat
  });
  return response.data as { token: string };
}

export async function login(email: string, password: string) {
  const response = await client.post("/auth/login/", { email, password });
  return response.data as { token: string };
}

export async function me() {
  const response = await client.get("/auth/me/");
  return response.data;
}

export async function logout() {
  await client.post("/auth/logout/");
  setAuthToken(null);
}

export async function getBooks(page = 1) {
  const response = await client.get(`/books/?page=${page}`);
  return response.data as {
    count: number;
    next: string | null;
    previous: string | null;
    results: {
      books: Book[];
      books_used: number;
      books_limit: number;
    };
  };
}

export async function getBook(bookId: number) {
  const response = await client.get(`/books/${bookId}/`);
  return response.data as Book;
}

export async function uploadBooks(files: File[], confirmRotation = false) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (confirmRotation) {
    formData.append("confirm_rotation", "true");
  }
  const response = await client.post("/books/upload/", formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    },
    validateStatus: (status) => status < 500
  });
  return response;
}

export async function deleteBook(bookId: number) {
  return client.delete(`/books/${bookId}/`);
}

export async function toggleProtectBook(bookId: number) {
  const response = await client.post(`/books/${bookId}/protect/`);
  return response.data as { is_protected: boolean };
}

export async function reanalyzeBook(bookId: number) {
  const response = await client.post(`/books/${bookId}/reanalyze/`);
  return response.data;
}

export async function getGlossary(bookId: number, page = 1, q = "", chapter = "") {
  const params = new URLSearchParams({ page: String(page) });
  if (q) params.append("q", q);
  if (chapter) params.append("chapter", chapter);
  const response = await client.get(`/books/${bookId}/glossary/?${params.toString()}`);
  return response.data as {
    count: number;
    next: string | null;
    previous: string | null;
    results: {
      book_id: number;
      views_count: number;
      terms: Term[];
    };
  };
}

export async function editTerm(bookId: number, termId: number, customDefinition: string) {
  const response = await client.patch(`/books/${bookId}/terms/${termId}/edit/`, {
    custom_definition: customDefinition
  });
  return response.data as Term;
}

export async function resetTerm(bookId: number, termId: number) {
  const response = await client.post(`/books/${bookId}/terms/${termId}/reset/`);
  return response.data as Term;
}

export async function globalSearch(query: string, page = 1) {
  const response = await client.get(`/search/?q=${encodeURIComponent(query)}&page=${page}`);
  return response.data as {
    count: number;
    next: string | null;
    previous: string | null;
    results: SearchResult[];
  };
}

export async function getStats() {
  const response = await client.get("/stats/");
  return response.data as {
    books_count: number;
    protected_books_count: number;
    limit: number;
    remaining_slots: number;
  };
}

export async function exportGlossary(bookId: number, format: "csv" | "txt" | "pdf") {
  const response = await client.get(`/books/${bookId}/export/?format=${format}`, {
    responseType: "blob"
  });
  return response.data as Blob;
}
