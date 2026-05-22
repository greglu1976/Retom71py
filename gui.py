# main.py (обновленная версия)
import time
import threading
import queue
import os
import sys
from datetime import datetime
from typing import List
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# Импорт драйвера и логгера
from RetomDriver import RetomDriver
from Logger import logger, LogLevel, LogEntry

# Импорт вашего драйвера Retom
try:
    from RetomDriver import RetomDriver
except ImportError:
    print("Ошибка: Не найден модуль RetomDriver. Убедитесь, что файл лежит рядом со скриптом.")
    sys.exit(1)


class RetomApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RETOM-71 Controller v2.0 (Tkinter)")
        self.root.geometry("1200x800")
        
        # Инициализация драйвера
        self.retom_driver = RetomDriver()
        
        # Очередь для передачи данных из рабочих потоков в GUI поток
        self.event_queue = queue.Queue()
        
        # Состояние
        self.is_running = True
        self.inputs_state = [False] * 16
        
        # Настройка интерфейса
        self._setup_ui()
        
        # Подключаем логгер к GUI
        logger.add_callback(self._on_log_message)
        logger.set_console_output(False)  # Включаем вывод в консоль
        
        # Установка callback для событий драйвера
        self.retom_driver.set_binary_inputs_callback(self._on_binary_inputs_event)
        
        # Запуск цикла обработки очереди событий
        self._process_queue()
        
        # Логируем запуск приложения
        logger.info("GUI", "Application started")

    def _setup_ui(self):
        """Создание элементов интерфейса"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Верхняя панель управления ---
        control_frame = ttk.LabelFrame(main_frame, text="Управление", padding="5")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        buttons_config = [
            ("Create", "Create"),
            ("Open", "Open"),
            ("Close", "Close"),
            ("Enable", "Enable"),
            ("Disable", "Disable"),
            ("Out61", "Out61")
        ]
        
        for label, cmd in buttons_config:
            btn = ttk.Button(control_frame, text=label, 
                             command=lambda c=cmd: self._execute_command(c))
            btn.pack(side=tk.LEFT, padx=5)
            
        # Статус бар
        self.status_var = tk.StringVar(value="Status: Not connected")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, foreground="blue")
        status_label.pack(side=tk.RIGHT, padx=10)
        
        # Кнопка очистки лога
        ttk.Button(control_frame, text="Clear Log", command=self._clear_log).pack(side=tk.RIGHT, padx=5)

        # --- Основная область (две колонки) ---
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Левая колонка: Входы - ВЕРТИКАЛЬНО
        inputs_frame = ttk.LabelFrame(content_frame, text="Binary Inputs Status", padding="5")
        inputs_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        inputs_frame.pack_propagate(False)
        inputs_frame.config(width=200)
        
        # Вертикальный список индикаторов In1-In16
        self.input_labels = []
        self.input_canvases = []
        
        list_frame = ttk.Frame(inputs_frame)
        list_frame.pack(padx=10, pady=5)
        
        for idx in range(16):
            cell_frame = ttk.Frame(list_frame, width=160, height=30)
            cell_frame.pack(fill=tk.X, pady=2)
            cell_frame.pack_propagate(False)
            
            canvas = tk.Canvas(cell_frame, width=20, height=20, bg='gray', highlightthickness=0)
            canvas.pack(side=tk.LEFT, padx=5)
            circle_id = canvas.create_oval(2, 2, 18, 18, fill='gray', outline='black')
            
            lbl = ttk.Label(cell_frame, text=f"In{idx+1}: OFF")
            lbl.pack(side=tk.LEFT, padx=5)
            
            self.input_canvases.append((canvas, circle_id))
            self.input_labels.append(lbl)

        # Правая колонка: Лог
        log_frame = ttk.LabelFrame(content_frame, text="Event Log", padding="5")
        log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=30, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Добавляем фильтры для лога
        filter_frame = ttk.Frame(log_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        self.log_filter_var = tk.StringVar(value="ALL")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.log_filter_var, 
                                     values=["ALL", "INFO", "WARNING", "ERROR", "DEBUG"],
                                     state="readonly", width=10)
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_log_filter())

    def _on_log_message(self, entry: LogEntry):
        """Callback для получения логов из логгера"""
        self.event_queue.put(('log', entry))

    def _apply_log_filter(self):
        """Применяет фильтр к отображаемым логам"""
        filter_level = self.log_filter_var.get()
        
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        
        for entry in logger.get_history():
            if filter_level == "ALL" or entry.level.value == filter_level:
                log_line = entry.format() + "\n"
                self.log_text.insert(tk.END, log_line)
                
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def _on_binary_inputs_event(self, nGroup: int, dwBinaryInput: int):
        """Callback вызывается из потока драйвера (COM thread).
        Кладем событие в очередь для обновления GUI в главном потоке."""
        self.event_queue.put(('binary_inputs', (nGroup, dwBinaryInput)))

    def _process_queue(self):
        """Периодически проверяет очередь событий и обновляет GUI."""
        try:
            while True:
                event_type, event_data = self.event_queue.get_nowait()
                
                if event_type == 'binary_inputs':
                    nGroup, dwBinaryInput = event_data
                    self._update_inputs_gui(dwBinaryInput)
                    
                elif event_type == 'log':
                    entry = event_data
                    self._add_log_to_gui(entry)
                    
        except queue.Empty:
            pass
        finally:
            if self.is_running:
                self.root.after(50, self._process_queue)

    def _update_inputs_gui(self, dwBinaryInput: int):
        """Обновляет виджеты входов в главном потоке"""
        for i in range(16):
            is_active = bool(dwBinaryInput & (1 << i))
            self.inputs_state[i] = is_active
            
            canvas, circle_id = self.input_canvases[i]
            lbl = self.input_labels[i]
            
            color = '#00FF00' if is_active else '#646464'
            text_status = "ON" if is_active else "OFF"
            
            canvas.itemconfig(circle_id, fill=color)
            lbl.config(text=f"In{i+1}: {text_status}")

    def _add_log_to_gui(self, entry: LogEntry):
        """Добавляет сообщение в текстовое поле лога"""
        current_filter = self.log_filter_var.get()
        
        # Если фильтр активен, проверяем нужно ли показывать
        if current_filter != "ALL" and entry.level.value != current_filter:
            return
            
        log_line = entry.format() + "\n"
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_line)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        
        # Обновляем статус при ошибках
        if entry.level == LogLevel.ERROR:
            self.status_var.set(f"Status: Error - {entry.message[:50]}")

    def _clear_log(self):
        logger.clear_history()
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        logger.info("GUI", "Log cleared")

    def _execute_command(self, command: str):
        """
        ВАЖНО: Все COM-операции выполняются в главном потоке Tkinter.
        Это необходимо для apartment-threaded COM.
        """
        try:
            if command == "Create":
                res = self.retom_driver.create_retom()
                if res:
                    self.status_var.set("Status: Created")
                else:
                    self.status_var.set(f"Status: Create failed - {self.retom_driver.st_error}")
                return
            
            # Для остальных команд
            self.retom_driver.st_function = command
            res = self.retom_driver.run_retom()
            
            if res:
                if command == "Open":
                    dev_info = ""
                    if self.retom_driver.retom and hasattr(self.retom_driver.retom, 'ServerInfo'):
                        info = self.retom_driver.retom.ServerInfo
                        dev_info = f" | Dev: {info.DeviceNumber}, Ver: {info.Version}"
                    self.status_var.set(f"Status: Open{dev_info}")
                elif command == "Close":
                    self.status_var.set("Status: Closed")
                elif command == "Enable":
                    self.status_var.set("Status: Enabled")
                elif command == "Disable":
                    self.status_var.set("Status: Disabled")
                elif command == "Out61":
                    self.status_var.set("Status: Out61 completed")
            else:
                self.status_var.set(f"Status: Error - {self.retom_driver.st_error}")
                
        except Exception as e:
            logger.error("GUI", f"Exception in '{command}': {str(e)}")
            self.status_var.set(f"Status: Exception - {str(e)[:50]}")

    def on_closing(self):
        """Обработчик закрытия окна"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            logger.info("GUI", "Application shutting down...")
            self.is_running = False
            try:
                if self.retom_driver.is_open:
                    self.retom_driver.st_function = "Close"
                    self.retom_driver.run_retom()
            except Exception as e:
                logger.error("GUI", f"Error during shutdown: {e}")
            finally:
                # Убираем callback при завершении
                logger.remove_callback(self._on_log_message)
                self.root.destroy()


def main():
    root = tk.Tk()
    
    style = ttk.Style()
    style.theme_use('clam')
    
    app = RetomApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()


if __name__ == "__main__":
    main()