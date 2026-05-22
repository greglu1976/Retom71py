import time
import threading
import queue
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional
import dearpygui.dearpygui as dpg

# Импорт вашего драйвера Retom
from RetomDriver import RetomDriver


@dataclass
class LogMessage:
    """Структура сообщения лога"""
    timestamp: datetime
    level: str  # INFO, WARNING, ERROR
    message: str


class RetomGUI:
    """Графический интерфейс для управления РЕТОМ"""
    
    def __init__(self):
        self.retom_driver = RetomDriver()
        self.is_running = True
        self.event_queue = queue.Queue()
        self.log_messages: List[LogMessage] = []
        self.max_log_messages = 1000
        
        # Состояния входов (16 штук)
        self.inputs_state = [False] * 16
        
        # ID виджетов
        self.input_circles = []
        self.input_texts = []
        
        # Запускаем обработчик событий
        self.retom_driver.set_binary_inputs_callback(self._on_binary_inputs)
    
    def _on_binary_inputs(self, nGroup: int, dwBinaryInput: int):
        """Callback из COM потока - помещаем событие в очередь"""
        self.event_queue.put(('binary_inputs', (nGroup, dwBinaryInput)))
    
    def _process_events(self):
        """Обработка событий из очереди (вызывается из GUI потока)"""
        try:
            while True:
                event_type, event_data = self.event_queue.get_nowait()
                
                if event_type == 'binary_inputs':
                    nGroup, dwBinaryInput = event_data
                    # Обновляем состояние входов
                    for i in range(16):
                        self.inputs_state[i] = bool(dwBinaryInput & (1 << i))
                    
                    # Обновляем GUI индикаторы
                    self._update_input_indicators()
                    
                elif event_type == 'log':
                    self._add_log_message(*event_data)
                    
        except queue.Empty:
            pass
    
    def _update_input_indicators(self):
        """Обновление индикаторов входов в GUI"""
        for i in range(16):
            color = (0, 255, 0, 255) if self.inputs_state[i] else (100, 100, 100, 255)
            if dpg.does_item_exist(f"input_circle_{i}"):
                dpg.configure_item(f"input_circle_{i}", fill=color, color=color)
                status = "ON" if self.inputs_state[i] else "OFF"
                if dpg.does_item_exist(f"input_text_{i}"):
                    dpg.set_value(f"input_text_{i}", f"In{i+1}: {status}")
    
    def _add_log_message(self, level: str, message: str):
        """Добавление сообщения в лог"""
        log_msg = LogMessage(
            timestamp=datetime.now(),
            level=level,
            message=message
        )
        self.log_messages.append(log_msg)
        
        # Ограничиваем количество сообщений
        if len(self.log_messages) > self.max_log_messages:
            self.log_messages.pop(0)
        
        # Обновляем лог в GUI
        self._update_log_display()
    
    def _update_log_display(self):
        """Обновление отображения лога"""
        if not dpg.does_item_exist("log_text"):
            return
        
        # Формируем текст лога
        log_text = ""
        for msg in self.log_messages[-self.max_log_messages:]:
            time_str = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
            
            # Иконки для уровней
            if msg.level == "ERROR":
                level_marker = "[ERROR]"
            elif msg.level == "WARNING":
                level_marker = "[WARNING]"
            else:
                level_marker = "[INFO]"
            
            log_text += f"[{time_str}] {level_marker} {msg.message}\n"
        
        dpg.set_value("log_text", log_text)
        
        # Автопрокрутка вниз
        if dpg.does_item_exist("log_child"):
            dpg.set_y_scroll("log_child", dpg.get_y_scroll_max("log_child"))
    
    def log_info(self, message: str):
        """Логирование информационного сообщения"""
        self.event_queue.put(('log', ('INFO', message)))
        print(f"[INFO] {message}")
    
    def log_warning(self, message: str):
        """Логирование предупреждения"""
        self.event_queue.put(('log', ('WARNING', message)))
        print(f"[WARNING] {message}")
    
    def log_error(self, message: str):
        """Логирование ошибки"""
        self.event_queue.put(('log', ('ERROR', message)))
        print(f"[ERROR] {message}")
    
    def _execute_retom_command(self, sender, app_data, command: str):
        """Выполнение команды РЕТОМ в отдельном потоке"""
        def execute():
            try:
                if command == "Create":
                    result = self.retom_driver.create_retom()
                    if result:
                        self.log_info("Retom created successfully")
                        self._update_status("Created")
                    else:
                        self.log_error(f"Failed to create Retom: {self.retom_driver.st_error}")
                    return
                
                self.retom_driver.st_function = command
                result = self.retom_driver.run_retom()
                
                if result:
                    self.log_info(f"Command '{command}' executed successfully")
                    if command == "Open":
                        self.log_info(f"Device opened successfully")
                        device_info = ""
                        if self.retom_driver.retom and hasattr(self.retom_driver.retom, 'ServerInfo'):
                            info = self.retom_driver.retom.ServerInfo
                            device_info = f" - Device: {info.DeviceNumber}, Version: {info.Version}"
                        self._update_status(f"Open{device_info}")
                    elif command == "Close":
                        self._update_status("Closed")
                    elif command == "Enable":
                        self._update_status("Enabled - Outputs active")
                    elif command == "Disable":
                        self._update_status("Disabled - Outputs inactive")
                else:
                    self.log_error(f"Command '{command}' failed: {self.retom_driver.st_error}")
                    self._update_status(f"Error: {self.retom_driver.st_error}")
                    
            except Exception as e:
                self.log_error(f"Exception in command '{command}': {e}")
        
        # Запускаем в отдельном потоке
        threading.Thread(target=execute, daemon=True).start()
    
    def _update_status(self, status: str):
        """Обновление строки статуса"""
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", f"Status: {status}")
    
    def setup_gui(self):
        """Настройка графического интерфейса"""
        dpg.create_context()
        
        # Пытаемся загрузить шрифт, если не получается - используем стандартный
        try:
            # Пробуем загрузить системный шрифт
            font_path = None
            
            # Пути к шрифтам в разных ОС
            if sys.platform == "win32":
                possible_fonts = [
                    "C:/Windows/Fonts/arial.ttf",
                    "C:/Windows/Fonts/consola.ttf",
                    "C:/Windows/Fonts/tahoma.ttf",
                    "C:/Windows/Fonts/verdana.ttf",
                    "C:/Windows/Fonts/calibri.ttf"
                ]
                for font in possible_fonts:
                    if os.path.exists(font):
                        font_path = font
                        break
            elif sys.platform == "darwin":  # macOS
                possible_fonts = [
                    "/System/Library/Fonts/SFNSText.ttf",
                    "/System/Library/Fonts/Helvetica.ttc"
                ]
                for font in possible_fonts:
                    if os.path.exists(font):
                        font_path = font
                        break
            else:  # Linux
                possible_fonts = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
                ]
                for font in possible_fonts:
                    if os.path.exists(font):
                        font_path = font
                        break
            
            if font_path and os.path.exists(font_path):
                with dpg.font_registry():
                    default_font = dpg.add_font(font_path, 16)
                    dpg.bind_font(default_font)
                print(f"Font loaded: {font_path}")
            else:
                print("Warning: No font file found, using default")
        except Exception as e:
            print(f"Font loading error (non-critical): {e}")
        
        # Основное окно
        with dpg.window(label="RETOM Controller", tag="main_window", width=1200, height=800):
            
            # Заголовок
            dpg.add_text("RETOM-71 Controller", color=(255, 200, 0), indent=10)
            dpg.add_spacer(height=10)
            
            # Верхняя панель с кнопками
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=lambda s, a: self._execute_retom_command(s, a, "Create"), width=100)
                dpg.add_button(label="Open", callback=lambda s, a: self._execute_retom_command(s, a, "Open"), width=100)
                dpg.add_button(label="Close", callback=lambda s, a: self._execute_retom_command(s, a, "Close"), width=100)
                dpg.add_button(label="Enable", callback=lambda s, a: self._execute_retom_command(s, a, "Enable"), width=100)
                dpg.add_button(label="Disable", callback=lambda s, a: self._execute_retom_command(s, a, "Disable"), width=100)
                dpg.add_button(label="Out61", callback=lambda s, a: self._execute_retom_command(s, a, "Out61"), width=100)
            
            dpg.add_spacer(height=10)
            
            # Статус
            self.status_text = dpg.add_text("Status: Not connected", tag="status_text")
            dpg.add_spacer(height=10)
            
            # Разделитель
            dpg.add_separator()
            dpg.add_spacer(height=10)
            
            # Основной контент: 2 колонки
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, resizable=True):
                dpg.add_table_column(width_stretch=True, init_width_or_weight=0.4)
                dpg.add_table_column(width_stretch=True, init_width_or_weight=0.6)
                
                with dpg.table_row():
                    # Левая колонка - состояние входов
                    with dpg.group():
                        dpg.add_text("Binary Inputs Status", color=(255, 200, 0))
                        dpg.add_spacer(height=5)
                        
                        # Сетка входов 4x4
                        with dpg.table(header_row=False, borders_innerH=True, borders_outerH=True,
                                      borders_innerV=True, borders_outerV=True):
                            for _ in range(4):
                                dpg.add_table_column(width_fixed=True, init_width_or_weight=150)
                            
                            for row in range(4):
                                with dpg.table_row():
                                    for col in range(4):
                                        idx = row * 4 + col
                                        with dpg.group(horizontal=True):
                                            # Индикатор (круг)
                                            with dpg.drawlist(width=25, height=25):
                                                circle = dpg.draw_circle(
                                                    (12, 12), 10,
                                                    color=(100, 100, 100, 255),
                                                    fill=(100, 100, 100, 255),
                                                    thickness=1,
                                                    tag=f"input_circle_{idx}"
                                                )
                                            # Текст
                                            text = dpg.add_text(f"In{idx+1}: OFF", tag=f"input_text_{idx}")
                                            self.input_circles.append(circle)
                                            self.input_texts.append(text)
                    
                    # Правая колонка - логгер
                    with dpg.group():
                        dpg.add_text("Event Log", color=(255, 200, 0))
                        dpg.add_spacer(height=5)
                        
                        with dpg.child_window(tag="log_child", height=500, border=True):
                            dpg.add_input_text(
                                tag="log_text",
                                multiline=True,
                                readonly=True,
                                width=-1,
                                height=500,
                                default_value=""
                            )
        
        # Устанавливаем primary window
        dpg.set_primary_window("main_window", True)
        
        # Настройка viewport
        dpg.create_viewport(title="RETOM Controller v1.0", width=1200, height=800)
        dpg.setup_dearpygui()
    
    def run(self):
        """Запуск GUI приложения"""
        self.setup_gui()
        
        # Создаем поток для обработки событий
        def event_loop():
            while self.is_running:
                self._process_events()
                time.sleep(0.05)
        
        event_thread = threading.Thread(target=event_loop, daemon=True)
        event_thread.start()
        
        # Основной цикл GUI
        dpg.show_viewport()
        
        # Рендеринг
        while dpg.is_dearpygui_running() and self.is_running:
            dpg.render_dearpygui_frame()
        
        dpg.destroy_context()
    
    def shutdown(self):
        """Завершение работы"""
        self.is_running = False
        if self.retom_driver.is_open:
            self.retom_driver.st_function = "Close"
            self.retom_driver.run_retom()


def main():
    """Главная функция"""
    app = RetomGUI()
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()