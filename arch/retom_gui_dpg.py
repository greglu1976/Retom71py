import time
import threading
import queue
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from typing import List

import dearpygui.dearpygui as dpg

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
    level: str
    message: str


class RetomApp:
    def __init__(self):
        self.retom_driver = RetomDriver()
        self.event_queue = queue.Queue()
        self.is_running = True
        self.inputs_state = [False] * 16
        self.log_messages: List[LogMessage] = []
        self.max_log_messages = 1000
        
        self.retom_driver.set_binary_inputs_callback(self._on_binary_inputs_event)
        self._setup_ui()

    def _setup_ui(self):
        """Создание элементов интерфейса Dear PyGui"""
        dpg.create_context()

        # Тема
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 220, 220, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (70, 70, 90, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (90, 90, 120, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (100, 100, 140, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (50, 50, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (40, 40, 55, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (50, 50, 70, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)

        dpg.bind_theme(global_theme)

        # Главное окно - resizable
        with dpg.window(
            label="RETOM-71 Controller v2.0",
            tag="main_window",
            width=1200,
            height=800,
            no_close=True,
            no_collapse=True,
            no_resize=False,
            no_move=False,
            no_title_bar=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True
        ):
            # --- Верхняя панель управления ---
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=lambda: self._execute_command("Create"), width=80, height=30)
                dpg.add_button(label="Open", callback=lambda: self._execute_command("Open"), width=80, height=30)
                dpg.add_button(label="Close", callback=lambda: self._execute_command("Close"), width=80, height=30)
                dpg.add_button(label="Enable", callback=lambda: self._execute_command("Enable"), width=80, height=30)
                dpg.add_button(label="Disable", callback=lambda: self._execute_command("Disable"), width=80, height=30)
                dpg.add_button(label="Out61", callback=lambda: self._execute_command("Out61"), width=80, height=30)

                dpg.add_spacer(width=20)
                self.status_text = dpg.add_text("Status: Not connected", color=(100, 150, 255, 255))

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # --- Основная область (две колонки) ---
            with dpg.group(horizontal=True):
                # Левая колонка: Входы - вертикальное расположение
                with dpg.child_window(
                    label="Binary Inputs Status",
                    width=200,
                    height=-1,  # растягивается по высоте
                    border=True
                ):
                    dpg.add_text("Binary Inputs", color=(180, 180, 180, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=5)

                    # 16 светодиодов ВЕРТИКАЛЬНО
                    self.input_texts = []
                    self.circle_tags = []

                    for idx in range(16):
                        with dpg.group(horizontal=True):
                            # Drawlist для кружка
                            with dpg.drawlist(width=20, height=20):
                                circ_tag = f"circ_{idx}"
                                dpg.draw_circle(
                                    center=(10, 10),
                                    radius=8,
                                    color=(100, 100, 100, 255),
                                    fill=(100, 100, 100, 255),
                                    tag=circ_tag
                                )
                                self.circle_tags.append(circ_tag)

                            dpg.add_spacer(width=8)
                            txt_tag = f"txt_{idx}"
                            dpg.add_text(f"In{idx+1}: OFF", tag=txt_tag)
                            self.input_texts.append(txt_tag)

                        if idx < 15:
                            dpg.add_spacer(height=4)

                dpg.add_spacer(width=10)

                # Правая колонка: Лог - растягивается
                with dpg.child_window(
                    label="Event Log",
                    width=-1,  # растягивается по ширине
                    height=-1,  # растягивается по высоте
                    border=True
                ):
                    dpg.add_text("Event Log", color=(180, 180, 180, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=5)

                    self.log_text = dpg.add_input_text(
                        multiline=True,
                        readonly=True,
                        width=-1,
                        height=-40,  # почти вся высота минус кнопка
                        tag="log_text"
                    )

                    dpg.add_spacer(height=5)
                    dpg.add_button(label="Clear Log", callback=self._clear_log, width=100)

        # Настройка viewport
        dpg.create_viewport(
            title="RETOM-71 Controller v2.0",
            width=1200,
            height=800,
            resizable=True  # окно можно изменять
        )
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)

    def _on_binary_inputs_event(self, nGroup: int, dwBinaryInput: int):
        """Callback из потока драйвера - кладем в очередь"""
        self.event_queue.put(('binary_inputs', (nGroup, dwBinaryInput)))

    def _process_queue(self):
        """Обработка очереди событий"""
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

    def _update_inputs_gui(self, dwBinaryInput: int):
        """Обновляет индикаторы входов - 16 светодиодов вертикально"""
        for i in range(16):
            # i=0 (In1, верхний) → бит 15 (старший, левый в строке лога)
            # i=15 (In16, нижний) → бит 0 (младший, правый в строке лога)
            bit_position = 15 - i
            is_active = bool(dwBinaryInput & (1 << bit_position))
            self.inputs_state[i] = is_active

            color = (0, 255, 0, 255) if is_active else (100, 100, 100, 255)
            text_status = "ON" if is_active else "OFF"

            dpg.configure_item(self.circle_tags[i], fill=color, color=color)
            dpg.set_value(self.input_texts[i], f"In{i+1}: {text_status}")
            
    def _add_log_to_gui(self, level: str, message: str):
        """Добавляет сообщение в лог"""
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

        current_text = dpg.get_value("log_text") or ""
        new_text = current_text + log_line
        dpg.set_value("log_text", new_text)

    def _clear_log(self):
        self.log_messages.clear()
        dpg.set_value("log_text", "")

    def _log_info(self, msg):
        self.event_queue.put(('log', ('INFO', msg)))
        print(f"[INFO] {msg}")

    def _log_error(self, msg):
        self.event_queue.put(('log', ('ERROR', msg)))
        print(f"[ERROR] {msg}")

    def _execute_command(self, command: str):
        """Выполнение команд"""
        try:
            if command == "Create":
                res = self.retom_driver.create_retom()
                if res:
                    self._log_info("Retom object created successfully")
                    dpg.set_value(self.status_text, "Status: Created")
                else:
                    self._log_error(f"Failed to create Retom: {self.retom_driver.st_error}")
                return

            self.retom_driver.st_function = command
            res = self.retom_driver.run_retom()

            if res:
                self._log_info(f"Command '{command}' executed OK")
                if command == "Open":
                    dev_info = ""
                    if self.retom_driver.retom and hasattr(self.retom_driver.retom, 'ServerInfo'):
                        info = self.retom_driver.retom.ServerInfo
                        dev_info = f" | Dev: {info.DeviceNumber}, Ver: {info.Version}"
                    dpg.set_value(self.status_text, f"Status: Open{dev_info}")
                elif command == "Close":
                    dpg.set_value(self.status_text, "Status: Closed")
                elif command == "Enable":
                    dpg.set_value(self.status_text, "Status: Enabled")
                elif command == "Disable":
                    dpg.set_value(self.status_text, "Status: Disabled")
            else:
                self._log_error(f"Command '{command}' failed: {self.retom_driver.st_error}")
                dpg.set_value(self.status_text, f"Status: Error - {self.retom_driver.st_error}")

        except Exception as e:
            self._log_error(f"Exception in '{command}': {str(e)}")

    def run(self):
        """Главный цикл"""
        while dpg.is_dearpygui_running() and self.is_running:
            self._process_queue()
            dpg.render_dearpygui_frame()
            time.sleep(0.01)

        self._cleanup()
        dpg.destroy_context()

    def _cleanup(self):
        """Закрытие приложения"""
        self.is_running = False
        try:
            if self.retom_driver.is_open:
                self.retom_driver.st_function = "Close"
                self.retom_driver.run_retom()
        except:
            pass


def main():
    app = RetomApp()
    app.run()


if __name__ == "__main__":
    main()