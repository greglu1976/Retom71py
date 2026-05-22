import time
import comtypes.client
import subprocess
import threading
from comtypes.client import GetEvents
from comtypes.gen import RTDI, RTLink

# Импорт pythoncom из pywin32
try:
    import pythoncom
except ImportError:
    print("Ошибка: Модуль pythoncom не найден. Установите pywin32: pip install pywin32")
    raise

RTDI_TLB = r".\RTDI\RTDI.tlb"
RTLINK_TLB = r".\RTDI\RTLink.tlb"

IP = "IP:192.168.11.146"
FREQ = 50.0


class RetomDriverEvents:
    """Класс-обработчик событий Retom"""
    
    def __init__(self, callback):
        self.callback = callback
    
    def BinaryInputsEvent(self, nGroup, dwBinaryInput):
        """Обработчик события изменения бинарных входов"""
        if self.callback:
            self.callback(nGroup, dwBinaryInput)
    
    def BinaryOutputsEvent(self, nGroup, dwBinaryOutput):
        """Обработчик события изменения бинарных выходов"""
        # Можно добавить при необходимости
        pass


class RetomDriver:
    def __init__(self):
        comtypes.client.GetModule(RTDI_TLB)
        comtypes.client.GetModule(RTLINK_TLB)

        self.retom = None
        self.is_open = 0
        self.st_error = ""
        self.st_result = ""
        self.st_function = ""
        self.result_return = ""
        self.contacts = [False] * 16
        
        # Для событий
        self.event_connection = None
        self.event_callback = None
        
        # Поток для обработки событий
        self.event_thread = None
        self.running = False
        self.message_pump_running = False

    def create_retom(self):
        """Создание COM-объекта Retom"""
        try:
            self.retom = comtypes.client.CreateObject(RTDI.DualServer, interface=RTDI.IDualServer)
            time.sleep(3.0)
            return True
        except Exception as e:
            self.st_error = f"Create Retom failed: {e}"
            print(self.st_error)
            return False


    def subscribe_events(self, callback):
        """Подписка на события Retom"""
        if not self.retom:
            print("Retom not initialized")
            return False
        
        self.event_callback = callback
        
        # Создаем обработчик событий
        event_handler = RetomDriverEvents(self._on_binary_inputs_event)
        
        # Подписываемся на события
        try:
            self.event_connection = GetEvents(self.retom, event_handler)
            print("Subscribed to Retom events")
            return True
        except Exception as e:
            print(f"Failed to subscribe to events: {e}")
            return False

    def _on_binary_inputs_event(self, nGroup, dwBinaryInput):
        """Внутренний обработчик событий"""
        if self.event_callback:
            # Вызываем callback в отдельном потоке, чтобы не блокировать COM
            threading.Thread(
                target=self.event_callback,
                args=(nGroup, dwBinaryInput),
                daemon=True
            ).start()

    def unsubscribe_events(self):
        """Отписка от событий"""
        if self.event_connection:
            self.event_connection = None
            print("Unsubscribed from Retom events")

    def run_retom(self):
        """Выполнение команды Retom"""
        self.st_result = ""
        
        if self.st_function == "Open":
            return self._open_connection()
        
        if self.is_open <= 0:
            print("Device not open")
            return False
            
        match self.st_function:
            case "SetOutContact":
                return self._set_out_contacts()
            case "Close":
                return self._close_connection()
            case "Enable":
                return self._enable_output()
            case "Disable":
                return self._disable_output()
            case "Out61":
                return self._out61()
            case _:
                self.st_error = f"Unknown function: {self.st_function}"
                return False

    def _open_connection(self):
        """Открытие соединения с устройством"""
        if self.retom is None:
            self.st_error = "Retom not initialized"
            print(self.st_error)
            return False
        
        try:
            # Закрываем предыдущее соединение если есть
            try:
                self.result_return = self.retom.close()
            except:
                pass
            
            self.result_return = self.retom.SetWorkParam("RetomType_66")
            
            self.is_open = self.retom.Open(IP, 0)
            
            if self.is_open == 1:
                print(f"Номер устройства: {self.retom.ServerInfo.DeviceNumber}")
                print(f"Версия ретом-мастера: {self.retom.ServerInfo.Version}")
                
                # После открытия подписываемся на события
                self.subscribe_events(self._on_binary_inputs)
                
                # Запускаем поток обработки сообщений COM
                self._start_message_pump()
                
                return True
            else:
                print("Устройство не подключено")
                self.retom = None
                self.st_error = "Failed to open device"
                return False
                
        except Exception as e:
            self.st_error = f"Error opening Retom: {e}"
            print(self.st_error)
            return False

    def _start_message_pump(self):
        """Запуск потока для обработки COM сообщений"""
        if self.event_thread and self.event_thread.is_alive():
            return
            
        self.message_pump_running = True
        self.event_thread = threading.Thread(target=self._message_pump, daemon=True)
        self.event_thread.start()
        print("Message pump thread started")

    def _message_pump(self):
        """Поток для обработки COM сообщений (необходим для событий)"""
        # Инициализируем COM в этом потоке
        pythoncom.CoInitialize()
        
        try:
            print("Message pump thread running")
            while self.message_pump_running and self.is_open:
                # Обрабатываем COM сообщения
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)  # Небольшая задержка для снижения нагрузки
            print("Message pump thread stopping")
        except Exception as e:
            print(f"Error in message pump: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _close_connection(self):
        """Закрытие соединения"""
        try:
            print("Closing connection...")
            
            # Останавливаем message pump
            self.message_pump_running = False
            
            # Отписываемся от событий
            self.unsubscribe_events()
            
            # Ждем завершения потока
            if self.event_thread and self.event_thread.is_alive():
                self.event_thread.join(timeout=2)
            
            # Закрываем соединение с устройством
            if self.retom:
                self.result_return = self.retom.Close()
                self.is_open = 0
                
            print("Connection closed")
            return True
        except Exception as e:
            self.st_error = f"Close error: {e}"
            print(self.st_error)
            return False

    def _enable_output(self):
        """Включение выходов"""
        try:
            self.result_return = self.retom.Enable()
            return True
        except Exception as e:
            self.st_error = f"Enable error: {e}"
            return False

    def _disable_output(self):
        """Отключение выходов"""
        try:
            self.result_return = self.retom.Disable()
            return True
        except Exception as e:
            self.st_error = f"Disable error: {e}"
            return False

    def _set_out_contacts(self):
        """Установка выходных контактов"""
        try:
            for num_cont, value in enumerate(self.contacts[:16]):
                self.result_return = self.retom.SetOutContact(num_cont, value)
            print(f"Set {len(self.contacts[:16])} output contacts")
            return True
        except Exception as e:
            self.st_error = f"SetOutContact error: {e}"
            return False

    def _out61(self):
        """Специальный режим Out61 (РЕТОМ-71)"""
        try:
            print("Starting Out61 mode...")
            
            # Основные каналы: Ua Ub Uc Ia Ib Ic
            ch_main = self.retom.NewAnalogChannels()
            ch_main.dFrequency = FREQ
            ch_main.SetSinSignal(0, 0, 0.0)    # Ua — фаза 0°
            ch_main.SetSinSignal(1, 0, 240.0)  # Ub — фаза 240°
            ch_main.SetSinSignal(2, 0, 120.0)  # Uc — фаза 120°
            ch_main.SetSinSignal(3, 1.0, 0.0)  # Ia — фаза 0°
            ch_main.SetSinSignal(4, 1.0, 240.0) # Ib — фаза 240°
            ch_main.SetSinSignal(5, 1.0, 120.0) # Ic — фаза 120°

            # Дополнительные каналы РЕТОМ-71: Ua2 Ub2 Uc2 Ia2 Ib2 Ic2
            ch_add = self.retom.NewAnalogChannels()
            ch_add.dFrequency = FREQ
            ch_add.SetSinSignal(0, 0.0, 0.0)   # Ua2
            ch_add.SetSinSignal(1, 0.0, 240.0) # Ub2
            ch_add.SetSinSignal(2, 0.0, 120.0) # Uc2
            ch_add.SetSinSignal(3, 0.0, 0.0)   # Ia2
            ch_add.SetSinSignal(4, 0.0, 240.0) # Ib2
            ch_add.SetSinSignal(5, 0.0, 120.0) # Ic2

            mask = 0x00770077

            self.retom.SetMaxUI(max(58, 58, 58) * 1.2, max(5, 5, 5) * 1.2)
            self.retom.ChannelsReset()
            time.sleep(1.0)

            result = self.retom.Out61(ch_main, mask, ch_add, mask)
            print(f"Out61 completed with result: {result}")
            return True
            
        except Exception as e:
            self.st_error = f"Out61 error: {e}"
            print(self.st_error)
            return False

    def _on_binary_inputs(self, nGroup, dwBinaryInput):
        """Callback для обработки события бинарных входов"""
        print(f"Binary Inputs Event - Group: {nGroup}, Value: {dwBinaryInput:016b}")
        
        # Вызываем внешний обработчик если установлен
        if hasattr(self, 'external_binary_inputs_callback') and self.external_binary_inputs_callback:
            try:
                self.external_binary_inputs_callback(nGroup, dwBinaryInput)
            except Exception as e:
                print(f"Error in external callback: {e}")

    def set_binary_inputs_callback(self, callback):
        """Установка внешнего обработчика событий бинарных входов"""
        self.external_binary_inputs_callback = callback
        print("Binary inputs callback set")

    def remove_retom(self):
        """Перезапуск соединения с Retom"""
        process_killed = False
        recreation_success = False
        
        try:
            print("Removing Retom...")
            
            # Останавливаем message pump и отписываемся от событий
            self.message_pump_running = False
            self.unsubscribe_events()
            
            # 1. Завершение процесса RTDI.exe
            try:
                result = subprocess.run(['taskkill', '/F', '/IM', 'RTDI.exe'], 
                                    capture_output=True, 
                                    text=True,
                                    timeout=5)
                
                if result.returncode == 0:
                    process_killed = True
                    print("RTDI.exe process killed successfully")
                    time.sleep(2)
                elif "not found" in result.stderr or "не найдена" in result.stderr:
                    process_killed = False
                    print("RTDI.exe process not found")
                else:
                    print(f"Taskkill returned: {result.returncode}, stderr: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print("Taskkill timeout")
            except FileNotFoundError:
                print("taskkill command not found (not Windows?)")
            
            # 2. Пересоздание соединения
            if process_killed or not self.is_open:
                # Закрываем существующее соединение
                if self.is_open and self.retom:
                    try:
                        self.retom.Close()
                        self.is_open = 0
                    except:
                        pass
                
                self.retom = None
                time.sleep(1)
                
                self.create_retom()
                self.st_function = "Open"
                recreation_success = self.run_retom()
            
            return recreation_success
            
        except Exception as ex:
            self.st_error = f"RemoveRetom failed: {ex}"
            print(self.st_error)
            return False


# Простой пример использования
def simple_event_handler(nGroup, dwBinaryInput):
    """Простой обработчик событий"""
    print(f"\n=== BINARY INPUTS EVENT ===")
    print(f"Group: {nGroup}")
    print(f"Binary Inputs: {dwBinaryInput:016b}")
    
    # Показываем активные входы
    active_inputs = []
    for i in range(16):
        if dwBinaryInput & (1 << i):
            active_inputs.append(str(i + 1))
    
    if active_inputs:
        print(f"Active inputs: {', '.join(active_inputs)}")
    else:
        print("No active inputs")
    print("===========================\n")


if __name__ == "__main__":
    print("=== Retom Driver Test ===\n")
    
    retom = RetomDriver()
    
    # Устанавливаем обработчик событий
    retom.set_binary_inputs_callback(simple_event_handler)
    
    # Создаем и открываем устройство
    print("1. Creating Retom...")
    retom.create_retom()
    
    print("2. Opening connection...")
    retom.st_function = "Open"
    if retom.run_retom():
        print("✓ Device opened successfully\n")
        
        # Включаем выходы
        print("3. Enabling outputs...")
        retom.st_function = "Enable"
        retom.run_retom()
        
        retom.st_function = "Out61"
        retom.run_retom()
        


        # Ждем и обрабатываем события
        print("\nListening for events... Press Ctrl+C to stop\n")
        try:
            while retom.is_open:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\nStopping...")
        
        # Отключаем выходы
        print("4. Disabling outputs...")
        retom.st_function = "Disable"
        retom.run_retom()
        
        # Закрываем соединение
        print("5. Closing connection...")
        retom.st_function = "Close"
        retom.run_retom()
    else:
        print(f"✗ Failed to open device: {retom.st_error}")
    
    print("\n=== Test Complete ===")