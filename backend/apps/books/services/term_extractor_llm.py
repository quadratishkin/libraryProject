from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict

import pymorphy3
from razdel import sentenize

# Для OpenAI
try:
    import openai
except ImportError:
    openai = None

# Для локальной LLM через llama-cpp-python
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

morph = pymorphy3.MorphAnalyzer()
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
CLEAN_SPACES_RE = re.compile(r"\s+")


@dataclass
class TermCandidate:
    """Класс для хранения кандидата в термины"""
    term: str
    normalized_term: str
    definition: str
    source_chapter: str
    source_paragraph_index: int
    source_quote: str
    frequency: int
    confidence: float = 0.0
    additional_context: str = ""


class LLMTermExtractor:
    """
    Извлечение терминов с помощью LLM (GPT, LLaMA, или другая модель)
    
    Поддерживаемые провайдеры:
    - openai: GPT-3.5/GPT-4
    - local: LLaMA/Codellama через llama-cpp-python
    - mock: Тестовый режим без реального API
    """
    
    def __init__(
        self,
        provider: str = "openai",  # openai, local, mock
        model_name: str = None,
        api_key: str = None,
        local_model_path: str = None,
        chunk_size: int = 2000,  # Максимальная длина текста для одного запроса
        temperature: float = 0.3,
    ):
        """
        Инициализация LLM экстрактора
        
        Args:
            provider: Провайдер LLM ('openai', 'local', 'mock')
            model_name: Название модели
            api_key: API ключ для OpenAI
            local_model_path: Путь к локальной модели GGUF
            chunk_size: Размер чанка для обработки
            temperature: Температура генерации (0-1)
        """
        self.provider = provider
        self.chunk_size = chunk_size
        self.temperature = temperature
        
        # Настройка моделей по умолчанию
        self.models = {
            "openai": model_name or "gpt-3.5-turbo",
            "local": model_name or "llama-2-7b-chat.Q4_K_M.gguf"
        }
        
        self._initialize_client(api_key, local_model_path)
        
    def _initialize_client(self, api_key: str = None, local_model_path: str = None):
        """Инициализация клиента LLM"""
        
        if self.provider == "openai":
            if openai is None:
                raise ImportError("Установите openai: pip install openai")
            
            self.client = openai.OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
            print(f"✓ OpenAI клиент инициализирован (модель: {self.models['openai']})")
            
        elif self.provider == "local":
            if Llama is None:
                raise ImportError("Установите llama-cpp-python: pip install llama-cpp-python")
            
            model_path = local_model_path or os.getenv("LLAMA_MODEL_PATH")
            if not model_path:
                raise ValueError("Укажите путь к локальной модели LLM")
            
            self.client = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_threads=4,
                verbose=False
            )
            print(f"✓ Локальная LLM загружена: {model_path}")
            
        elif self.provider == "mock":
            print("⚠ Используется mock режим (тестовый)")
            self.client = None
            
        else:
            raise ValueError(f"Неизвестный провайдер: {provider}")
    
    def extract_terms(self, book_structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Извлекает термины из структуры книги с помощью LLM
        """
        all_terms = []
        word_frequency = self._collect_frequency(book_structure)
        
        # Обрабатываем книгу по главам
        for chapter in book_structure:
            chapter_title = chapter.get("chapter_title") or "Без названия главы"
            chapter_text = self._prepare_chapter_text(chapter)
            
            if not chapter_text:
                continue
            
            # Разбиваем главу на чанки
            chunks = self._split_into_chunks(chapter_text)
            
            for chunk_idx, chunk in enumerate(chunks):
                terms = self._extract_from_chunk(
                    chunk, 
                    chapter_title, 
                    chunk_idx,
                    word_frequency
                )
                all_terms.extend(terms)
        
        # Дедупликация
        return self._deduplicate_and_format(all_terms)
    
    def _prepare_chapter_text(self, chapter: dict) -> str:
        """Подготавливает текст главы для отправки в LLM"""
        paragraphs = chapter.get("paragraphs", [])
        return "\n".join(paragraphs)
    
    def _split_into_chunks(self, text: str) -> list[str]:
        """Разбивает текст на чанки для обработки"""
        chunks = []
        current_chunk = ""
        
        for sentence in sentenize(text):
            if len(current_chunk) + len(sentence.text) < self.chunk_size:
                current_chunk += " " + sentence.text
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence.text
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _extract_from_chunk(
        self,
        chunk: str,
        chapter_title: str,
        chunk_idx: int,
        word_frequency: Dict
    ) -> list[TermCandidate]:
        """Извлекает термины из одного чанка"""
        
        prompt = self._build_extraction_prompt(chunk)
        
        try:
            response = self._call_llm(prompt)
            parsed_terms = self._parse_llm_response(response)
            
            candidates = []
            for term_data in parsed_terms:
                term = term_data.get("term", "")
                definition = term_data.get("definition", "")
                confidence = term_data.get("confidence", 0.7)
                
                if not term or not definition:
                    continue
                
                normalized = self._normalize_term(term)
                frequency = self._estimate_term_frequency(normalized, word_frequency)
                
                candidates.append(TermCandidate(
                    term=term,
                    normalized_term=normalized,
                    definition=definition,
                    source_chapter=chapter_title,
                    source_paragraph_index=chunk_idx,
                    source_quote=chunk[:500],
                    frequency=max(1, frequency),
                    confidence=confidence,
                    additional_context=term_data.get("context", "")
                ))
            
            return candidates
            
        except Exception as e:
            print(f"Ошибка при LLM извлечении: {e}")
            return []
    
    def _build_extraction_prompt(self, text: str) -> str:
        """Строит промпт для LLM"""
        
        prompt = f"""Ты - эксперт по извлечению терминов и определений из текста.
Проанализируй следующий текст и найди все термины с их определениями.

Правила:
1. Термин - это ключевое понятие, слово или фраза, которая вводится или объясняется
2. Определение - это объяснение значения термина
3. Игнорируй общеизвестные термины
4. Извлекай только явные определения

Формат ответа: JSON массив объектов с полями:
- term: термин (строка)
- definition: определение (строка)
- confidence: уверенность от 0 до 1 (число)
- context: контекст в котором встретился термин (строка)

Текст для анализа:
{text}

Ответ (только JSON, без лишнего текста):"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """Выполняет запрос к LLM"""
        
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.models["openai"],
                messages=[
                    {"role": "system", "content": "Ты - эксперт по извлечению терминов. Отвечай только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=2000
            )
            return response.choices[0].message.content
            
        elif self.provider == "local":
            response = self.client(
                prompt,
                max_tokens=2000,
                temperature=self.temperature,
                echo=False
            )
            return response["choices"][0]["text"]
            
        elif self.provider == "mock":
            # Mock ответ для тестирования
            return self._mock_response(prompt)
        
        return "[]"
    
    def _mock_response(self, prompt: str) -> str:
        """Генерирует тестовый ответ для mock режима"""
        
        return json.dumps([
            {
                "term": "Инкапсуляция",
                "definition": "Принцип ООП, скрывающий внутреннее состояние объекта",
                "confidence": 0.95,
                "context": "Инкапсуляция - это один из основных принципов ООП"
            },
            {
                "term": "Полиморфизм",
                "definition": "Способность объектов с одинаковым интерфейсом иметь разную реализацию",
                "confidence": 0.92,
                "context": "Полиморфизм позволяет использовать единый интерфейс для разных типов"
            }
        ], ensure_ascii=False)
    
    def _parse_llm_response(self, response: str) -> list[dict]:
        """Парсит JSON ответ от LLM"""
        
        # Очищаем ответ от лишнего текста
        response = response.strip()
        
        # Удаляем markdown код если есть
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        
        response = response.strip()
        
        try:
            terms = json.loads(response)
            if isinstance(terms, list):
                return terms
            elif isinstance(terms, dict) and "terms" in terms:
                return terms["terms"]
            else:
                return []
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON: {e}")
            # Пробуем извлечь JSON из строки
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            return []
    
    def _normalize_term(self, term: str) -> str:
        """Нормализует термин"""
        words = WORD_RE.findall(term.lower())
        normalized = []
        for word in words:
            if word.isdigit():
                normalized.append(word)
            else:
                try:
                    parsed = morph.parse(word)[0]
                    normalized.append(parsed.normal_form)
                except:
                    normalized.append(word)
        return " ".join(normalized)
    
    def _collect_frequency(self, book_structure: list[dict]) -> Dict[str, int]:
        """Собирает частотность слов"""
        counter = {}
        for chapter in book_structure:
            for paragraph in chapter.get("paragraphs", []):
                for word in WORD_RE.findall(paragraph.lower()):
                    if word.isdigit():
                        continue
                    counter[word] = counter.get(word, 0) + 1
        return counter
    
    def _estimate_term_frequency(self, term_normalized: str, word_frequency: Dict) -> int:
        """Оценивает частоту термина"""
        if not term_normalized:
            return 1
        words = term_normalized.split()
        if len(words) == 1:
            return word_frequency.get(words[0], 1)
        return min((word_frequency.get(word, 1) for word in words), default=1)
    
    def _deduplicate_and_format(self, terms: list[TermCandidate]) -> list[dict]:
        """Дедупликация и форматирование результатов"""
        unique = {}
        
        for term in terms:
            key = term.normalized_term
            if key not in unique or term.confidence > unique[key].confidence:
                unique[key] = term
        
        return [
            {
                "term": t.term,
                "normalized_term": t.normalized_term,
                "definition": t.definition,
                "source_chapter": t.source_chapter,
                "source_paragraph_index": t.source_paragraph_index,
                "source_quote": t.source_quote[:500],
                "frequency": t.frequency,
                "llm_confidence": t.confidence,
                "additional_context": t.additional_context,
            }
            for t in sorted(unique.values(), key=lambda x: x.term.lower())
        ]


# ========== Функция-обертка для обратной совместимости ==========

def extract_terms_llm(
    book_structure: list[dict[str, Any]],
    provider: str = "mock",  # 'openai', 'local', 'mock'
    api_key: str = None,
    model_name: str = None,
    local_model_path: str = None
) -> list[dict[str, Any]]:
    """
    Главная функция для извлечения терминов через LLM
    
    Args:
        book_structure: Структура книги
        provider: Провайдер ('openai', 'local', 'mock')
        api_key: API ключ для OpenAI
        model_name: Название модели
        local_model_path: Путь к локальной модели
    """
    extractor = LLMTermExtractor(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        local_model_path=local_model_path
    )
    return extractor.extract_terms(book_structure)


# Пример использования:
# from apps.books.services.term_extractor_llm import extract_terms_llm
# 
# # Использование OpenAI
# terms = extract_terms_llm(
#     book_structure,
#     provider="openai",
#     api_key="your-api-key",
#     model_name="gpt-3.5-turbo"
# )
# 
# # Использование локальной модели
# terms = extract_terms_llm(
#     book_structure,
#     provider="local",
#     local_model_path="C:/models/llama-2-7b-chat.Q4_K_M.gguf"
# )
# 
# # Mock режим для тестирования
# terms = extract_terms_llm(book_structure, provider="mock")