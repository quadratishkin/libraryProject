from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

import pymorphy3
import torch
from razdel import sentenize
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# Загружаем морфологический анализатор
morph = pymorphy3.MorphAnalyzer()

# Регулярные выражения
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
CLEAN_SPACES_RE = re.compile(r"\s+")

# Стоп-слова (краткий список для фильтрации)
STOP_WORDS = {
    "это", "и", "в", "на", "к", "с", "по", "как", "под", "для",
    "или", "из", "о", "об", "а", "но", "то", "что", "так", "же",
}

# Fallback паттерны для извлечения определения из контекста
FALLBACK_PATTERNS = [
    re.compile(r"^(?P<term>[^.!?]{1,120}?)\s*[-—]\s*это\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[^.!?]{1,120}?)\s+это\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[^.!?]{1,120}?)\s+называется\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[^.!?]{1,120}?)\s+представляет собой\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^под\s+(?P<term>[^.!?]{1,120}?)\s+понимается\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[^.!?]{1,120}?)\s+является\s+(?P<def>.+)$", re.IGNORECASE),
]


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


class AITermExtractor:
    """Извлечение терминов с помощью ruBERT NER модели"""
    
    def __init__(self, use_gpu: bool = False, fallback_to_rules: bool = True):
        """
        Инициализация AI экстрактора
        
        Args:
            use_gpu: Использовать GPU если доступен
            fallback_to_rules: Использовать rule-based методы если AI не сработал
        """
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        self.fallback_to_rules = fallback_to_rules
        self.model_name = "bond005/rubert-multiconer"  # ruBERT для русского языка
        
        self._load_model()
        
    def _load_model(self):
        """Загружает модель ruBERT"""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            self.ner_pipeline = pipeline(
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                device=self.device,
                aggregation_strategy="simple"  # Объединяет части терминов в один
            )
            print(f"✓ Модель {self.model_name} успешно загружена")
        except Exception as e:
            print(f"✗ Ошибка загрузки модели: {e}")
            self.ner_pipeline = None
    
    def extract_terms(self, book_structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Извлекает термины из структуры книги с помощью AI
        
        Args:
            book_structure: Структура книги из fb2_parser
            
        Returns:
            Список терминов с определениями
        """
        if self.ner_pipeline is None:
            print("Модель не загружена, использую rule-based метод")
            return self._extract_terms_fallback(book_structure)
        
        word_frequency = self._collect_frequency(book_structure)
        deduplicated: dict[str, TermCandidate] = {}
        paragraph_index = 0
        
        for chapter in book_structure:
            chapter_title = chapter.get("chapter_title") or "Без названия главы"
            
            for paragraph in chapter.get("paragraphs", []):
                paragraph_index += 1
                
                # Разбиваем на предложения
                for sentence in split_to_sentences(paragraph):
                    # AI извлечение терминов
                    ai_terms = self._extract_with_ai(sentence, chapter_title, paragraph_index)
                    
                    for ai_term in ai_terms:
                        normalized = normalize_term(ai_term.term)
                        if not normalized:
                            continue
                        
                        frequency = self._estimate_term_frequency(normalized, word_frequency)
                        ai_term.frequency = max(1, frequency)
                        
                        existing = deduplicated.get(normalized)
                        if not existing or ai_term.confidence > existing.confidence:
                            deduplicated[normalized] = ai_term
                    
                    # Если AI не нашел термины и включен fallback
                    if not ai_terms and self.fallback_to_rules:
                        rule_terms = self._extract_with_rules(sentence, chapter_title, paragraph_index)
                        
                        for rule_term in rule_terms:
                            normalized = normalize_term(rule_term.term)
                            if not normalized:
                                continue
                            
                            frequency = self._estimate_term_frequency(normalized, word_frequency)
                            rule_term.frequency = max(1, frequency)
                            
                            if normalized not in deduplicated:
                                deduplicated[normalized] = rule_term
        
        return self._format_output(deduplicated)
    
    def _extract_with_ai(self, sentence: str, chapter_title: str, paragraph_index: int) -> list[TermCandidate]:
        """Извлекает термины с помощью NER модели"""
        candidates = []
        
        try:
            # Ограничиваем длину предложения для модели
            if len(sentence) > 512:
                sentence = sentence[:512]
            
            # Запускаем NER
            entities = self.ner_pipeline(sentence)
            
            for entity in entities:
                term = entity.get('word', '')
                confidence = entity.get('score', 0.0)
                entity_group = entity.get('entity_group', '')
                
                # Фильтруем сущности
                if self._is_valid_term_candidate(term, confidence, entity_group):
                    # Находим определение для этого термина
                    definition = self._extract_definition_from_context(sentence, term)
                    
                    if definition:
                        candidates.append(TermCandidate(
                            term=term,
                            normalized_term=normalize_term(term),
                            definition=definition,
                            source_chapter=chapter_title,
                            source_paragraph_index=paragraph_index,
                            source_quote=sentence,
                            frequency=1,
                            confidence=confidence
                        ))
        except Exception as e:
            print(f"Ошибка при AI извлечении: {e}")
        
        return candidates
    
    def _extract_with_rules(self, sentence: str, chapter_title: str, paragraph_index: int) -> list[TermCandidate]:
        """Извлекает термины с помощью rule-based методов (fallback)"""
        candidates = []
        sentence_clean = sanitize_text(sentence)
        
        for pattern in FALLBACK_PATTERNS:
            match = pattern.match(sentence_clean)
            if not match:
                continue
            
            term = clean_term(match.group("term"))
            if not valid_term(term):
                continue
            
            definition = sentence_clean
            
            candidates.append(TermCandidate(
                term=term,
                normalized_term=normalize_term(term),
                definition=definition,
                source_chapter=chapter_title,
                source_paragraph_index=paragraph_index,
                source_quote=sentence_clean,
                frequency=1,
                confidence=0.6  # Меньшая уверенность для rule-based
            ))
            break
        
        return candidates
    
    def _extract_definition_from_context(self, sentence: str, term: str) -> str:
        """Извлекает определение для термина из контекста предложения"""
        # Сначала пробуем найти определение по шаблонам
        for pattern in FALLBACK_PATTERNS:
            match = pattern.match(sanitize_text(sentence))
            if match and match.group("term").strip().lower() in term.lower():
                return match.group("def").strip()
        
        # Если не нашли, возвращаем всё предложение как определение
        return sentence
    
    def _is_valid_term_candidate(self, term: str, confidence: float, entity_group: str) -> bool:
        """Проверяет, является ли сущность подходящим термином"""
        # Проверка доверия
        if confidence < 0.7:
            return False
        
        # Проверка длины
        if len(term) < 3 or len(term) > 60:
            return False
        
        # Проверка что не цифры
        if term.isdigit():
            return False
        
        # Проверка стоп-слов
        if term.lower() in STOP_WORDS:
            return False
        
        # Разрешенные типы сущностей для ruBERT-multiconer
        allowed_groups = ["ORG", "PROD", "MISC", "LOC", "PER"]
        if entity_group and entity_group not in allowed_groups:
            return False
        
        return True
    
    def _collect_frequency(self, book_structure: list[dict[str, Any]]) -> Counter[str]:
        """Собирает частотность слов в книге"""
        normalized_words = []
        for chapter in book_structure:
            for paragraph in chapter.get("paragraphs", []):
                for word in WORD_RE.findall(paragraph.lower()):
                    if word.isdigit():
                        continue
                    try:
                        normalized_words.append(morph.parse(word)[0].normal_form)
                    except:
                        pass
        return Counter(normalized_words)
    
    def _estimate_term_frequency(self, term_normalized: str, word_frequency: Counter[str]) -> int:
        """Оценивает частоту термина"""
        if not term_normalized:
            return 0
        words = term_normalized.split()
        if len(words) == 1:
            return word_frequency.get(words[0], 1)
        return min((word_frequency.get(word, 1) for word in words), default=1)
    
    def _format_output(self, deduplicated: dict[str, TermCandidate]) -> list[dict[str, Any]]:
        """Форматирует вывод"""
        return [
            {
                "term": candidate.term,
                "normalized_term": candidate.normalized_term,
                "definition": candidate.definition,
                "source_chapter": candidate.source_chapter,
                "source_paragraph_index": candidate.source_paragraph_index,
                "source_quote": candidate.source_quote,
                "frequency": candidate.frequency,
                "ai_confidence": candidate.confidence,
            }
            for candidate in sorted(deduplicated.values(), key=lambda item: item.term.lower())
        ]
    
    def _extract_terms_fallback(self, book_structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fallback на оригинальный rule-based метод"""
        from .term_extractor import extract_terms as original_extract
        return original_extract(book_structure)


# ========== Вспомогательные функции (совместимость с оригиналом) ==========

def sanitize_text(text: str) -> str:
    """Очищает текст от HTML тегов"""
    text = re.sub(r"<[^>]+>", " ", text)
    return CLEAN_SPACES_RE.sub(" ", text).strip()


def split_to_sentences(text: str) -> list[str]:
    """Разбивает текст на предложения"""
    sanitized = sanitize_text(text)
    return [fragment.text.strip() for fragment in sentenize(sanitized) if fragment.text.strip()]


def normalize_term(term: str) -> str:
    """Нормализует термин (начальная форма)"""
    words = WORD_RE.findall(term.lower())
    normalized_words = []
    for word in words:
        if word.isdigit():
            normalized_words.append(word)
            continue
        try:
            parsed = morph.parse(word)[0]
            normalized_words.append(parsed.normal_form)
        except:
            normalized_words.append(word)
    return " ".join(normalized_words).strip()


def clean_term(raw_term: str) -> str:
    """Очищает термин от лишних символов"""
    term = sanitize_text(raw_term)
    term = term.strip(".,:;!?\"'()[]{}")
    term = term.replace("  ", " ")
    words = WORD_RE.findall(term)
    words = words[:4]
    return " ".join(words).strip()


def valid_term(term: str) -> bool:
    """Проверяет валидность термина"""
    if len(term) < 2:
        return False
    if term.isdigit():
        return False
    low = term.lower()
    if low in STOP_WORDS:
        return False
    words = [w.lower() for w in WORD_RE.findall(term)]
    if not words:
        return False
    return True


def is_noun_phrase(candidate: str) -> bool:
    """Проверяет является ли фраза именной"""
    words = [w for w in WORD_RE.findall(candidate.lower()) if w]
    if not words or len(words) > 4:
        return False
    try:
        parsed_words = [morph.parse(word)[0] for word in words if not word.isdigit()]
        if not parsed_words:
            return False
        return any("NOUN" in p.tag for p in parsed_words)
    except:
        return True


def extract_terms(book_structure: list[dict[str, Any]], use_ai: bool = True) -> list[dict[str, Any]]:
    """
    Главная функция для извлечения терминов
    
    Args:
        book_structure: Структура книги
        use_ai: Использовать AI (True) или rule-based (False)
    """
    if use_ai:
        extractor = AITermExtractor(fallback_to_rules=True)
        return extractor.extract_terms(book_structure)
    else:
        # Импорт оригинальной функции для обратной совместимости
        from .term_extractor_original import extract_terms as original_extract
        return original_extract(book_structure)