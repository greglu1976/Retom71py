import time
import threading
import queue
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from typing import List
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# Импорт вашего драйвера Retom
try:
    from RetomDriver import RetomDriver
except ImportError:
    print("Ошибка: Не найден модуль RetomDriver2. Убедитесь, что файл лежит рядом со скриптом.")
    sys.exit(1)


@dataclass
class LogMessage:
    """Структура сообщения лога"""
    timestamp: datetime
    level: str  # INFO, WARNING, ERROR
    message: str


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
        self.log_messages: List[LogMessage] = []
        self.max_log_messages = 1000
        
        # Настройка интерфейса
        self._setup_ui()
        
        # Установка callback для событий драйвера
        self.retom_driver.set_binary_inputs_callback(self._on_binary_inputs_event)
        
        # Запуск цикла обработки очереди событий
        self._process_queue()

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

        # --- Основная область (две колонки) ---
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Левая колонка: Входы
        inputs_frame = ttk.LabelFrame(content_frame, text="Binary Inputs Status", padding="5")
        inputs_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Сетка индикаторов 4x4
        self.input_labels = []
        self.input_canvases = []
        
        grid_frame = ttk.Frame(inputs_frame)
        grid_frame.pack(expand=True)
        
        for row in range(4):
            for col in range(4):
                idx = row * 4 + col
                
                cell_frame = ttk.Frame(grid_frame, width=120, height=40)
                cell_frame.grid(row=row, column=col, padx=5, pady=5)
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
        
        ttk.Button(log_frame, text="Clear Log", command=self._clear_log).pack(anchor=tk.E, pady=5)

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
                    level, message = event_data
                    self._add_log_to_gui(level, message)
                    
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

    def _add_log_to_gui(self, level: str, message: str):
        """Добавляет сообщение в текстовое поле лога"""
        log_msg = LogMessage(
            timestamp=datetime.now(),
            level=level,
            message=message
        )
        self.log_messages.append(log_msg)
        
        if len(self.log_messages) > self.max_log_messages:
            self.log_messages.pop(0)
            
        time_str = log_msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        if level == "ERROR":
            marker = "[ERROR]"
        elif level == "WARNING":
            marker = "[WARNING]"
        else:
            marker = "[INFO]"
            
        log_line = f"[{time_str}] {marker} {message}\n"
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_line)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def _clear_log(self):
        self.log_messages.clear()
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def _log_info(self, msg):
        self.event_queue.put(('log', ('INFO', msg)))
        print(f"[INFO] {msg}")

    def _log_error(self, msg):
        self.event_queue.put(('log', ('ERROR', msg)))
        print(f"[ERROR] {msg}")

    def _execute_command(self, command: str):
        """
        ВАЖНО: Все COM-операции выполняются в главном потоке Tkinter.
        Это необходимо для apartment-threaded COM.
        """
        try:
            if command == "Create":
                res = self.retom_driver.create_retom()
                if res:
                    self._log_info("Retom object created successfully")
                    self.status_var.set("Status: Created")
                else:
                    self._log_error(f"Failed to create Retom: {self.retom_driver.st_error}")
                return
            
            # Для остальных команд
            self.retom_driver.st_function = command
            res = self.retom_driver.run_retom()
            
            if res:
                self._log_info(f"Command '{command}' executed OK")
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
            else:
                self._log_error(f"Command '{command}' failed: {self.retom_driver.st_error}")
                self.status_var.set(f"Status: Error - {self.retom_driver.st_error}")
                
        except Exception as e:
            self._log_error(f"Exception in '{command}': {str(e)}")

    def on_closing(self):
        """Обработчик закрытия окна"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.is_running = False
            try:
                if self.retom_driver.is_open:
                    self.retom_driver.st_function = "Close"
                    self.retom_driver.run_retom()
            except:
                pass
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