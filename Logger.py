# logger.py
import time
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import List, Callable, Optional
from enum import Enum

class LogLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"

@dataclass
class LogEntry:
    """Структура записи лога"""
    timestamp: datetime
    level: LogLevel
    module: str
    message: str
    
    def format(self) -> str:
        """Форматирует запись лога для вывода"""
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        return f"[{time_str}] [{self.level.value}] [{self.module}] {self.message}"


class RetomLogger:
    """
    Универсальный логгер для приложения Retom.
    Поддерживает несколько уровней логирования и callback'и для GUI.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton паттерн для единого логгера во всем приложении"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RetomLogger, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._callbacks: List[Callable[[LogEntry], None]] = []
        self._log_history: List[LogEntry] = []
        self._max_history = 1000
        self._console_output = True
        self._file_output = None
        self._file_lock = threading.Lock()
        
    def set_console_output(self, enabled: bool):
        """Включить/выключить вывод в консоль"""
        self._console_output = enabled
        
    def set_file_output(self, filepath: Optional[str]):
        """Установить файл для записи логов"""
        self._file_output = filepath
        
    def add_callback(self, callback: Callable[[LogEntry], None]):
        """Добавить callback для получения всех логов (например для GUI)"""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: Callable[[LogEntry], None]):
        """Удалить callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    def _add_entry(self, level: LogLevel, module: str, message: str):
        """Внутренний метод добавления записи лога"""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            module=module,
            message=message
        )
        
        # Сохраняем в историю
        self._log_history.append(entry)
        if len(self._log_history) > self._max_history:
            self._log_history.pop(0)
            
        # Выводим в консоль
        if self._console_output:
            print(entry.format())
            
        # Записываем в файл
        if self._file_output:
            try:
                with self._file_lock:
                    with open(self._file_output, 'a', encoding='utf-8') as f:
                        f.write(entry.format() + '\n')
            except Exception as e:
                print(f"Failed to write log to file: {e}")
                
        # Вызываем все callback'и
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                print(f"Error in log callback: {e}")
                
    def info(self, module: str, message: str):
        """Логирование информационного сообщения"""
        self._add_entry(LogLevel.INFO, module, message)
        
    def warning(self, module: str, message: str):
        """Логирование предупреждения"""
        self._add_entry(LogLevel.WARNING, module, message)
        
    def error(self, module: str, message: str):
        """Логирование ошибки"""
        self._add_entry(LogLevel.ERROR, module, message)
        
    def debug(self, module: str, message: str):
        """Логирование отладочного сообщения"""
        self._add_entry(LogLevel.DEBUG, module, message)
        
    def get_history(self, level: Optional[LogLevel] = None, module: Optional[str] = None) -> List[LogEntry]:
        """Получить историю логов с фильтрацией"""
        filtered = self._log_history
        
        if level:
            filtered = [e for e in filtered if e.level == level]
            
        if module:
            filtered = [e for e in filtered if e.module == module]
            
        return filtered.copy()
        
    def clear_history(self):
        """Очистить историю логов"""
        self._log_history.clear()
        
    def get_last_error(self) -> Optional[LogEntry]:
        """Получить последнюю ошибку"""
        for entry in reversed(self._log_history):
            if entry.level == LogLevel.ERROR:
                return entry
        return None


# Создаем глобальный экземпляр для удобного импорта
logger = RetomLogger()