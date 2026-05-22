# main.py (три колонки: управление/параметры, лог, светодиоды)
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
        self.root.title("RETOM-71 Controller v2.1 (Tkinter)")
        self.root.geometry("2000x1100")
        
        # Инициализация драйвера
        self.retom_driver = RetomDriver()
        
        # Очередь для передачи данных из рабочих потоков в GUI поток
        self.event_queue = queue.Queue()
        
        # Состояние
        self.is_running = True
        self.inputs_state = [False] * 16
        
        # Словарь для хранения переменных гармоник
        self.harmonics_vars = {}
        
        # Настройка интерфейса
        self._setup_ui()
        
        # Подключаем логгер к GUI
        logger.add_callback(self._on_log_message)
        logger.set_console_output(False)
        
        # Установка callback для событий драйвера
        self.retom_driver.set_binary_inputs_callback(self._on_binary_inputs_event)
        
        # Запуск цикла обработки очереди событий
        self._process_queue()
        
        # Логируем запуск приложения
        logger.info("GUI", "Application started")

    def _setup_ui(self):
        """Создание элементов интерфейса"""
        # Создаем основной контейнер с прокруткой
        main_canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        self.scrollable_frame = ttk.Frame(main_canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Привязываем колесико мыши
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Основной фрейм с тремя колонками
        main_frame = ttk.Frame(self.scrollable_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === КОЛОНКА 1: Управление и параметры сигналов ===
        column1 = ttk.Frame(main_frame, width=600)
        column1.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        
        # Панель управления (без статуса)
        control_frame = ttk.LabelFrame(column1, text="Управление", padding="5")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        buttons_config = [
            ("Create", "Create"),
            ("Open", "Open"),
            ("Close", "Close"),
            ("Enable", "Enable"),
            ("Disable", "Disable"),
            ("Out61", "Out61"),
            ("Out61HQ", "Out61HQ"),  # Новая кнопка для гармоник
            ("Kill", "Kill")          # Новая кнопка для принудительного завершения
        ]
        
        for label, cmd in buttons_config:
            btn = ttk.Button(control_frame, text=label, 
                           command=lambda c=cmd: self._execute_command(c))
            btn.pack(side=tk.LEFT, padx=5)
        
        # Область параметров сигналов
        signals_frame = ttk.LabelFrame(column1, text="Параметры сигналов Out61", padding="5")
        signals_frame.pack(fill=tk.BOTH, expand=True)
        
        # Канал 1
        channel1_frame = ttk.LabelFrame(signals_frame, text="Канал 1 (Основной - Выходы 1-6)", padding="5")
        channel1_frame.pack(fill=tk.X, pady=(0, 5))
        self._create_channel_widgets(channel1_frame, "channel1")
        
        # Канал 2
        channel2_frame = ttk.LabelFrame(signals_frame, text="Канал 2 (Дополнительный - Выходы 7-12)", padding="5")
        channel2_frame.pack(fill=tk.X, pady=(0, 5))
        self._create_channel_widgets(channel2_frame, "channel2")
        
        # Гармоники
        harmonics_frame = ttk.LabelFrame(signals_frame, text="Высшие гармоники (2-я и 5-я)", padding="5")
        harmonics_frame.pack(fill=tk.X)
        self._create_harmonics_widgets(harmonics_frame)
        
        # Кнопка применения параметров
        apply_btn = ttk.Button(signals_frame, text="Применить все параметры к драйверу", 
                               command=self._apply_all_params)
        apply_btn.pack(pady=10)
        
        # === КОЛОНКА 2: Журнал (лог) ===
        column2 = ttk.Frame(main_frame, width=700)
        column2.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        column2.pack_propagate(False)
        
        log_frame = ttk.LabelFrame(column2, text="Event Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Фильтры для лога и кнопка очистки (в одной строке)
        filter_frame = ttk.Frame(log_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        self.log_filter_var = tk.StringVar(value="ALL")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.log_filter_var, 
                                     values=["ALL", "INFO", "WARNING", "ERROR", "DEBUG"],
                                     state="readonly", width=10)
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_log_filter())
        
        # Кнопка Clear Log рядом с фильтром
        clear_log_btn = ttk.Button(filter_frame, text="Clear Log", command=self._clear_log)
        clear_log_btn.pack(side=tk.LEFT, padx=5)
        
        # === КОЛОНКА 3: Светодиоды (Binary Inputs) - БЕЗ ПРОКРУТКИ ===
        column3 = ttk.Frame(main_frame, width=400)
        column3.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        column3.pack_propagate(False)
        
        inputs_frame = ttk.LabelFrame(column3, text="Binary Inputs Status", padding="5")
        inputs_frame.pack(fill=tk.BOTH, expand=True)
        
        # Простой фрейм без прокрутки для светодиодов
        inputs_container = ttk.Frame(inputs_frame)
        inputs_container.pack(fill=tk.BOTH, expand=True)
        
        # Создаем индикаторы (без Canvas с прокруткой)
        self.input_labels = []
        self.input_canvases = []
        
        for idx in range(16):
            cell_frame = ttk.Frame(inputs_container, height=35)
            cell_frame.pack(fill=tk.X, pady=3)
            cell_frame.pack_propagate(False)
            
            canvas = tk.Canvas(cell_frame, width=22, height=22, bg='gray', highlightthickness=0)
            canvas.pack(side=tk.LEFT, padx=8)
            circle_id = canvas.create_oval(3, 3, 19, 19, fill='gray', outline='black')
            
            lbl = ttk.Label(cell_frame, text=f"In{idx+1}: OFF", font=("Arial", 10))
            lbl.pack(side=tk.LEFT, padx=5)
            
            self.input_canvases.append((canvas, circle_id))
            self.input_labels.append(lbl)
        
        # === Строка статуса внизу (отдельно от колонок) ===
        status_frame = ttk.Frame(self.scrollable_frame, relief=tk.SUNKEN, padding="5")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Status: Not connected")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                 foreground="blue", font=("Arial", 10, "bold"))
        status_label.pack(side=tk.LEFT)
        
        # Добавляем разделитель и время
        ttk.Separator(status_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        
        self.time_var = tk.StringVar()
        time_label = ttk.Label(status_frame, textvariable=self.time_var, foreground="gray")
        time_label.pack(side=tk.RIGHT)
        self._update_time()
        
        # Инициализируем поля значениями из драйвера
        self._load_params_from_driver()
    
    def _update_time(self):
        """Обновляет время в статусной строке"""
        self.time_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if self.is_running:
            self.root.after(1000, self._update_time)

    def _create_channel_widgets(self, parent, channel_name):
        """Создает виджеты для ввода параметров канала"""
        # Словарь для хранения переменных
        if not hasattr(self, 'signal_vars'):
            self.signal_vars = {}
        
        self.signal_vars[channel_name] = {}
        
        # Создаем фрейм с 2 колонками
        left_frame = ttk.Frame(parent)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        right_frame = ttk.Frame(parent)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Параметры напряжений
        voltage_frame = ttk.LabelFrame(left_frame, text="Напряжения (U)", padding="5")
        voltage_frame.pack(fill=tk.X, pady=5)
        
        voltage_params = [
            ("Ua (Амплитуда, В):", "amplUA", 0.0, 300.0),
            ("Ua (Угол, град):", "anglUA", -360.0, 360.0),
            ("Ub (Амплитуда, В):", "amplUB", 0.0, 300.0),
            ("Ub (Угол, град):", "anglUB", -360.0, 360.0),
            ("Uc (Амплитуда, В):", "amplUC", 0.0, 300.0),
            ("Uc (Угол, град):", "anglUC", -360.0, 360.0),
        ]
        
        for label_text, param_name, min_val, max_val in voltage_params:
            frame = ttk.Frame(voltage_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=label_text, width=20).pack(side=tk.LEFT)
            
            var = tk.DoubleVar(value=self.retom_driver.signals[channel_name][param_name])
            entry = ttk.Entry(frame, textvariable=var, width=12)
            entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(frame, text=f"[{min_val}..{max_val}]").pack(side=tk.LEFT)
            
            self.signal_vars[channel_name][param_name] = var
        
        # Частота (перенесена в левую колонку под напряжения)
        freq_frame = ttk.LabelFrame(left_frame, text="Частота", padding="5")
        freq_frame.pack(fill=tk.X, pady=5)
        
        frame = ttk.Frame(freq_frame)
        frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(frame, text="Частота (Гц):", width=20).pack(side=tk.LEFT)
        
        var = tk.DoubleVar(value=self.retom_driver.signals[channel_name]["freq"])
        entry = ttk.Entry(frame, textvariable=var, width=12)
        entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(frame, text="[10.0..200.0]").pack(side=tk.LEFT)
        
        self.signal_vars[channel_name]["freq"] = var
        
        # Параметры токов
        current_frame = ttk.LabelFrame(right_frame, text="Токи (I)", padding="5")
        current_frame.pack(fill=tk.X, pady=5)
        
        current_params = [
            ("Ia (Амплитуда, А):", "amplIA", 0.0, 100.0),
            ("Ia (Угол, град):", "anglIA", -360.0, 360.0),
            ("Ib (Амплитуда, А):", "amplIB", 0.0, 100.0),
            ("Ib (Угол, град):", "anglIB", -360.0, 360.0),
            ("Ic (Амплитуда, А):", "amplIC", 0.0, 100.0),
            ("Ic (Угол, град):", "anglIC", -360.0, 360.0),
        ]
        
        for label_text, param_name, min_val, max_val in current_params:
            frame = ttk.Frame(current_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=label_text, width=20).pack(side=tk.LEFT)
            
            var = tk.DoubleVar(value=self.retom_driver.signals[channel_name][param_name])
            entry = ttk.Entry(frame, textvariable=var, width=12)
            entry.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(frame, text=f"[{min_val}..{max_val}]").pack(side=tk.LEFT)
            
            self.signal_vars[channel_name][param_name] = var

    def _create_harmonics_widgets(self, parent):
        """Создает виджеты для ввода параметров гармоник"""
        # Информационная метка
        info_label = ttk.Label(parent, 
                               text="Настройка амплитуд 2-й и 5-й гармоник для напряжений",
                               foreground="blue")
        info_label.pack(pady=(0, 10))
        
        # Создаем таблицу гармоник
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill=tk.X, padx=10)
        
        # Заголовки
        headers = ["Фаза", "2-я гармоника (В)", "5-я гармоника (В)"]
        for col, header in enumerate(headers):
            ttk.Label(table_frame, text=header, font=("Arial", 9, "bold")).grid(
                row=0, column=col, padx=10, pady=5, sticky="w")
        
        # Строки для каждой фазы
        phases = [
            ("Фаза A", "amplA2harm", "amplA5harm"),
            ("Фаза B", "amplB2harm", "amplB5harm"),
            ("Фаза C", "amplC2harm", "amplC5harm")
        ]
        
        for row, (phase_name, param_2harm, param_5harm) in enumerate(phases, start=1):
            # Название фазы
            ttk.Label(table_frame, text=phase_name).grid(
                row=row, column=0, padx=10, pady=5, sticky="w")
            
            # Поле для 2-й гармоники
            var_2harm = tk.DoubleVar(value=0.0)
            entry_2harm = ttk.Entry(table_frame, textvariable=var_2harm, width=15)
            entry_2harm.grid(row=row, column=1, padx=10, pady=5)
            
            # Поле для 5-й гармоники
            var_5harm = tk.DoubleVar(value=0.0)
            entry_5harm = ttk.Entry(table_frame, textvariable=var_5harm, width=15)
            entry_5harm.grid(row=row, column=2, padx=10, pady=5)
            
            # Добавляем подсказки
            ttk.Label(table_frame, text="[0..100 В]").grid(
                row=row, column=1, padx=(10, 0), pady=5, sticky="e")
            ttk.Label(table_frame, text="[0..100 В]").grid(
                row=row, column=2, padx=(10, 0), pady=5, sticky="e")
            
            # Сохраняем переменные
            self.harmonics_vars[param_2harm] = var_2harm
            self.harmonics_vars[param_5harm] = var_5harm
        
        # Кнопки управления гармониками
        harmonics_buttons_frame = ttk.Frame(parent)
        harmonics_buttons_frame.pack(pady=10)
        
        ttk.Button(harmonics_buttons_frame, text="Применить гармоники", 
                  command=self._apply_harmonics).pack(side=tk.LEFT, padx=5)
        ttk.Button(harmonics_buttons_frame, text="Сбросить гармоники", 
                  command=self._reset_harmonics).pack(side=tk.LEFT, padx=5)
        
        # Примечание
        note_label = ttk.Label(parent, 
                               text="Примечание: 2-я гармоника (100 Гц), 5-я гармоника (250 Гц) при частоте 50 Гц",
                               foreground="gray", font=("Arial", 8))
        note_label.pack(pady=(5, 0))

    def _load_params_from_driver(self):
        """Загружает параметры из драйвера в GUI переменные"""
        # Загружаем основные сигналы
        if hasattr(self, 'signal_vars'):
            for channel in ["channel1", "channel2"]:
                if channel in self.signal_vars:
                    for param_name, var in self.signal_vars[channel].items():
                        var.set(self.retom_driver.signals[channel][param_name])
        
        # Загружаем гармоники
        try:
            for param_name, var in self.harmonics_vars.items():
                if hasattr(self.retom_driver, 'signals_hq'):
                    value = self.retom_driver.signals_hq["channel_hq"].get(param_name, 0.0)
                    var.set(value)
        except Exception as e:
            logger.error("GUI", f"Error loading harmonics: {e}")

    def _apply_all_params(self):
        """Применяет все параметры (сигналы и гармоники) к драйверу"""
        self._apply_signal_params()
        self._apply_harmonics()

    def _apply_signal_params(self):
        """Применяет параметры сигналов из GUI в драйвер"""
        try:
            for channel in ["channel1", "channel2"]:
                for param_name, var in self.signal_vars[channel].items():
                    value = var.get()
                    # Проверка допустимых значений
                    if param_name == "freq":
                        if value < 10.0 or value > 200.0:
                            logger.warning("GUI", f"{channel}.{param_name} = {value} вне диапазона [10..200]")
                    elif "amplU" in param_name:
                        if value < 0.0 or value > 300.0:
                            logger.warning("GUI", f"{channel}.{param_name} = {value} вне диапазона [0..300]")
                    elif "amplI" in param_name:
                        if value < 0.0 or value > 100.0:
                            logger.warning("GUI", f"{channel}.{param_name} = {value} вне диапазона [0..100]")
                    
                    self.retom_driver.signals[channel][param_name] = value
            
            logger.info("GUI", "Signal parameters applied successfully")
            messagebox.showinfo("Успех", "Параметры сигналов применены")
        except Exception as e:
            logger.error("GUI", f"Error applying signal parameters: {e}")
            messagebox.showerror("Ошибка", f"Ошибка применения параметров: {e}")

    def _apply_harmonics(self):
        """Применяет настройки гармоник к драйверу"""
        try:
            for param_name, var in self.harmonics_vars.items():
                value = var.get()
                if value < 0:
                    value = 0
                if value > 100:
                    value = 100
                    logger.warning("GUI", f"{param_name} ограничен 100 В")
                
                self.retom_driver.signals_hq["channel_hq"][param_name] = value
            
            logger.info("GUI", "Harmonics parameters applied successfully")
            messagebox.showinfo("Успех", "Параметры гармоник применены")
        except Exception as e:
            logger.error("GUI", f"Error applying harmonics: {e}")
            messagebox.showerror("Ошибка", f"Ошибка применения гармоник: {e}")

    def _reset_harmonics(self):
        """Сбрасывает все гармоники в 0"""
        for var in self.harmonics_vars.values():
            var.set(0.0)
        logger.info("GUI", "Harmonics reset to zero")
        messagebox.showinfo("Успех", "Гармоники сброшены в 0")

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
        """Callback вызывается из потока драйвера"""
        self.event_queue.put(('binary_inputs', (nGroup, dwBinaryInput)))

    def _process_queue(self):
        """Периодически проверяет очередь событий и обновляет GUI"""
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
        
        if current_filter != "ALL" and entry.level.value != current_filter:
            return
            
        log_line = entry.format() + "\n"
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_line)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        
        if entry.level == LogLevel.ERROR:
            self.status_var.set(f"Status: Error - {entry.message[:50]}")
            # Меняем цвет на красный при ошибке
            # Цвет меняется через 5 секунд обратно на синий
            self.root.after(5000, lambda: self.status_var.set(self.status_var.get().replace("Error", "Status")))

    def _clear_log(self):
        logger.clear_history()
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        logger.info("GUI", "Log cleared")

    def _execute_command(self, command: str):
        """Выполнение команд"""
        try:
            # Обработка специальной команды Kill
            if command == "Kill":
                if messagebox.askyesno("Подтверждение", "Принудительно завершить процесс RTDI.exe?\nЭто может быть необходимо при зависании."):
                    logger.info("GUI", "Executing Kill command...")
                    result = self.retom_driver.remove_retom()
                    if result:
                        self.status_var.set("Status: Process killed and recreated")
                        logger.info("GUI", "Kill command completed successfully")
                    else:
                        self.status_var.set(f"Status: Kill failed - {self.retom_driver.st_error}")
                        logger.error("GUI", f"Kill command failed: {self.retom_driver.st_error}")
                return
            
            # Обработка команды Create
            if command == "Create":
                res = self.retom_driver.create_retom()
                if res:
                    self.status_var.set("Status: Created")
                else:
                    self.status_var.set(f"Status: Create failed - {self.retom_driver.st_error}")
                return
            
            # Обработка команды Out61HQ (с гармониками)
            
            # Обычные команды
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
                elif command == "Out61HQ":
                    self.status_var.set("Status: Out61HQ completed")                    
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