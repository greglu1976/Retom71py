import time
import comtypes.client
import subprocess
import threading
from comtypes.client import GetEvents
from comtypes.gen import RTDI #, RTLink
import pythoncom
import sys

from Logger import logger  # Импортируем логгер

RTDI_TLB = r".\RTDI.tlb"
RTLINK_TLB = r".\RTLink.tlb"


FREQ = 50.0

# Определяем MODULE_NAME перед использованием
MODULE_NAME = "RetomDriver"

class RetomDriverEvents:
    """Класс-обработчик событий Retom"""
    
    def __init__(self, callback):
        self.callback = callback
    
    def BinaryInputsEvent(self, nGroup, dwBinaryInput):
        """Обработчик события изменения бинарных входов"""
        if self.callback:
            self.callback(nGroup, dwBinaryInput)
    
    def BinaryOutputsEvent(self, nGroup, dwBinaryOutput):
        logger.debug(MODULE_NAME, f"BinaryOutputsEvent: Group={nGroup}, Value={dwBinaryOutput}")


class RetomDriver:
    def __init__(self, ip ="IP:192.168.11.146" ):
        # Загружаем модули TLB один раз при создании экземпляра
        try:
            comtypes.client.GetModule(RTDI_TLB)
            comtypes.client.GetModule(RTLINK_TLB)
            logger.info(MODULE_NAME, "TLB modules loaded successfully")            
        except Exception as e:
            logger.error(MODULE_NAME, f"Could not load TLB modules: {e}")

        self.IP = ip
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

        # Внешний callback для бинарных входов
        self.external_binary_inputs_callback = None

        # Сигналы для выдачи

        self.signals = {
            "channel1": {
                "freq": 50.0,
                "amplUA": 0.0,
                "anglUA": 0.0,
                "amplUB": 0.0,
                "anglUB": 240.0,   
                "amplUC": 0.0,
                "anglUC": 120.0,
                "amplIA": 1.0,
                "anglIA": 0.0,
                "amplIB": 1.0,
                "anglIB": 240.0,   
                "amplIC": 1.0,
                "anglIC": 120.0,                                                       
            },
            "channel2": {
                "freq": 50.0,
                "amplUA": 0.0,
                "anglUA": 0.0,
                "amplUB": 0.0,
                "anglUB": 240.0,   
                "amplUC": 0.0,
                "anglUC": 120.0,
                "amplIA": 0.0,
                "anglIA": 0.0,
                "amplIB": 0.0,
                "anglIB": 240.0,   
                "amplIC": 0.0,
                "anglIC": 120.0,                                                       
            },
        }

        self.signals_hq = {
            "channel_hq": {
                "amplA2harm": 1.0,
                "amplB2harm": 0.0,
                "amplC2harm": 0.0,
                "amplA5harm": 1.0,
                "amplB5harm": 0.0,
                "amplC5harm": 0.0,                                                      
            },
        }


    def _ensure_com_initialized(self):
        """
        Безопасная инициализация COM в текущем потоке.
        """
        try:
            hr = pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            if hr not in (None, 0, 1):
                raise Exception(f"CoInitializeEx failed with HRESULT: {hr}")
            logger.debug(MODULE_NAME, "COM initialized in current thread")
        except Exception as e:
            err_str = str(e)
            if "already initialized" in err_str.lower() or "different model" in err_str.lower():
                logger.debug(MODULE_NAME, "COM already initialized")
            else:
                logger.warning(MODULE_NAME, f"Warning during COM init: {e}")

    def create_retom(self):

        logger.info(MODULE_NAME, "Creating Retom COM object...")        
        """Создание COM-объекта Retom"""
        # 1. Инициализируем COM в ЭТОМ потоке
        self._ensure_com_initialized()
        
        try:
            self.retom = comtypes.client.CreateObject(RTDI.DualServer, interface=RTDI.IDualServer)
            self.retom.SetMaxUI(max(58, 58, 58) * 1.2, max(5, 5, 5) * 1.2)
            logger.info(MODULE_NAME, "COM object created successfully")            
            # Даем драйверу время на запуск процесса RTDI.exe
            time.sleep(2.0) 
            
            # Проверка, жив ли процесс (опционально)
            try:
                output = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq RTDI.exe'], stderr=subprocess.STDOUT)
                if b'RTDI.exe' in output:
                    logger.info(MODULE_NAME, "RTDI.exe process is running")
                else:
                    logger.warning(MODULE_NAME, "RTDI.exe process NOT found after creation!")
            except Exception as e:
                logger.debug(MODULE_NAME, f"Could not check RTDI.exe process: {e}")

            return True
        except Exception as e:
            self.st_error = f"Create Retom failed: {e}"
            logger.error(MODULE_NAME, self.st_error)
            return False

    def subscribe_events(self, callback):
        """Подписка на события Retom"""
        if not self.retom:
            logger.error(MODULE_NAME, "Cannot subscribe: Retom not initialized")
            return False
        
        self.event_callback = callback
        
        # Создаем обработчик событий
        event_handler = RetomDriverEvents(self._on_binary_inputs_event)
        
        try:
            self._ensure_com_initialized()
            self.event_connection = GetEvents(self.retom, event_handler)
            logger.info(MODULE_NAME, "Subscribed to Retom events")
            return True
        except Exception as e:
            logger.error(MODULE_NAME, f"Failed to subscribe to events: {e}")
            return False

    def _on_binary_inputs_event(self, nGroup, dwBinaryInput):
        """Внутренний обработчик событий"""
        logger.debug(MODULE_NAME, f"BinaryInputsEvent received: Group={nGroup}, Value={dwBinaryInput:016b}")        
        """Внутренний обработчик событий"""
        if self.event_callback:
            threading.Thread(
                target=self.event_callback,
                args=(nGroup, dwBinaryInput),
                daemon=True
            ).start()

    def unsubscribe_events(self):
        """Отписка от событий"""
        if self.event_connection:
            try:
                self.event_connection = None
                logger.info(MODULE_NAME, "Unsubscribed from Retom events")                
            except Exception as e:
                logger.warning(MODULE_NAME, f"Error unsubscribing: {e}")

    def run_retom(self):
        """Выполнение команды Retom"""
        logger.info(MODULE_NAME, f"Executing command: {self.st_function}")        
        self.st_result = ""
        
        if self.st_function == "Open":
            return self._open_connection()
        
        if self.is_open <= 0:
            logger.error(MODULE_NAME, "Device not open, cannot execute command")
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
            case "Out61HQ":
                return self._out61_hq()            
            case _:
                self.st_error = f"Unknown function: {self.st_function}"
                logger.error(MODULE_NAME, self.st_error)
                return False

    def _open_connection(self):
        """Открытие соединения с устройством"""
        if self.retom is None:
            self.st_error = "Retom not initialized"
            logger.error(MODULE_NAME, self.st_error)
            return False
        
        # Инициализируем COM в потоке, который выполняет Open
        self._ensure_com_initialized()
        
        try:
            # Закрываем предыдущее соединение если есть
            try:
                self.result_return = self.retom.Close()
                logger.debug(MODULE_NAME, "Previous connection closed")                
            except:
                pass
            
            self.result_return = self.retom.SetWorkParam("RetomType_66")
            logger.debug(MODULE_NAME, "Work param set to RetomType_66")            
            
            logger.info(MODULE_NAME, f"Attempting to open connection to {self.IP}...")
            self.is_open = self.retom.Open(self.IP, 0)
            
            if self.is_open == 1:
                device_number = self.retom.ServerInfo.DeviceNumber
                version = self.retom.ServerInfo.Version
                logger.info(MODULE_NAME, f"Device opened - Number: {device_number}, Version: {version}")  

                # После открытия подписываемся на события
                self.subscribe_events(self._on_binary_inputs)
                
                # Запускаем поток обработки сообщений COM
                self._start_message_pump()
                
                return True
            else:
                logger.error(MODULE_NAME, "Failed to open device (Open returned != 1)")
                self.retom = None
                self.st_error = "Failed to open device"
                return False
                
        except Exception as e:
            self.st_error = f"Error opening Retom: {e}"
            logger.error(MODULE_NAME, self.st_error)
            return False

    def _start_message_pump(self):
        """Запуск потока для обработки COM сообщений"""
        if self.event_thread and self.event_thread.is_alive():
            logger.debug(MODULE_NAME, "Message pump already running")            
            return
            
        self.message_pump_running = True
        self.event_thread = threading.Thread(target=self._message_pump, daemon=True)
        self.event_thread.start()
        logger.info(MODULE_NAME, "Message pump thread started")

    def _message_pump(self):
        """Поток для обработки COM сообщений (необходим для событий)"""
        self._ensure_com_initialized()
        
        try:
            logger.info(MODULE_NAME, "Message pump thread running")
            while self.message_pump_running and self.is_open:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.05)
            logger.info(MODULE_NAME, "Message pump thread stopping")
        except Exception as e:
            logger.error(MODULE_NAME, f"Error in message pump: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except:
                pass

    def _close_connection(self):
        """Закрытие соединения"""
        self._ensure_com_initialized()

        try:
            logger.info(MODULE_NAME, "Closing connection...")
            
            self.message_pump_running = False
            self.unsubscribe_events()
            
            if self.event_thread and self.event_thread.is_alive():
                self.event_thread.join(timeout=2)
                logger.debug(MODULE_NAME, "Message pump thread joined")
            
            if self.retom:
                self.result_return = self.retom.Close()
                self.is_open = 0
                
            logger.info(MODULE_NAME, "Connection closed successfully")
            return True
        except Exception as e:
            self.st_error = f"Close error: {e}"
            logger.error(MODULE_NAME, self.st_error)
            return False

    def _enable_output(self):
        """Включение выходов"""
        self._ensure_com_initialized()
        try:
            self.result_return = self.retom.Enable()
            logger.info(MODULE_NAME, "Outputs enabled")            
            return True
        except Exception as e:
            self.st_error = f"Enable error: {e}"
            logger.error(MODULE_NAME, self.st_error)            
            return False

    def _disable_output(self):
        """Отключение выходов"""
        self._ensure_com_initialized()
        try:
            self.result_return = self.retom.Disable()
            logger.info(MODULE_NAME, "Outputs disabled")            
            return True
        except Exception as e:
            self.st_error = f"Disable error: {e}"
            logger.error(MODULE_NAME, self.st_error)            
            return False

    def _set_out_contacts(self):
        """Установка выходных контактов"""
        self._ensure_com_initialized()
        try:
            for num_cont, value in enumerate(self.contacts[:16]):
                self.result_return = self.retom.SetOutContact(num_cont, value)
            logger.info(MODULE_NAME, f"Set {len(self.contacts[:16])} output contacts")
            return True
        except Exception as e:
            self.st_error = f"SetOutContact error: {e}"
            logger.error(MODULE_NAME, self.st_error)            
            return False

    def _out61(self):
        """Специальный режим Out61 (РЕТОМ-71)"""
        self._ensure_com_initialized()
        try:
            logger.info(MODULE_NAME, "Starting Out61 mode...")
            
            ch_main = self.retom.NewAnalogChannels()
            ch_main.dFrequency = self.signals["channel1"]["freq"]
            ch_main.SetSinSignal(0, self.signals["channel1"]["amplUA"], self.signals["channel1"]["anglUA"])    # Ua
            ch_main.SetSinSignal(1, self.signals["channel1"]["amplUB"], self.signals["channel1"]["anglUB"])    # Ub
            ch_main.SetSinSignal(2, self.signals["channel1"]["amplUC"], self.signals["channel1"]["anglUC"])    # Uc
            ch_main.SetSinSignal(3, self.signals["channel1"]["amplIA"], self.signals["channel1"]["anglIA"])    # Ia
            ch_main.SetSinSignal(4, self.signals["channel1"]["amplIB"], self.signals["channel1"]["anglIB"])    # Ib
            ch_main.SetSinSignal(5, self.signals["channel1"]["amplIC"], self.signals["channel1"]["anglIC"])    # Ic

            ch_add = self.retom.NewAnalogChannels()
            ch_add.dFrequency = self.signals["channel2"]["freq"]
            ch_add.SetSinSignal(0, self.signals["channel2"]["amplUA"], self.signals["channel2"]["anglUA"])  # Ua2
            ch_add.SetSinSignal(1, self.signals["channel2"]["amplUB"], self.signals["channel2"]["anglUB"])  # Ub2
            ch_add.SetSinSignal(2, self.signals["channel2"]["amplUC"], self.signals["channel2"]["anglUC"])  # Uc2
            ch_add.SetSinSignal(3, self.signals["channel2"]["amplIA"], self.signals["channel2"]["anglIA"])  # Ia2
            ch_add.SetSinSignal(4, self.signals["channel2"]["amplIB"], self.signals["channel2"]["anglIB"])  # Ib2
            ch_add.SetSinSignal(5, self.signals["channel2"]["amplIC"], self.signals["channel2"]["anglIC"])  # Ic2

            mask = 0x00770077

            #self.retom.SetMaxUI(max(58, 58, 58) * 1.2, max(5, 5, 5) * 1.2)
            #self.retom.ChannelsReset()
            #time.sleep(1.0)

            result = self.retom.Out61(ch_main, mask, ch_add, mask)
            logger.info(MODULE_NAME, f"Out61 completed with result: {result}")
            return True
            
        except Exception as e:
            self.st_error = f"Out61 error: {e}"
            logger.error(MODULE_NAME, self.st_error)
            return False


    def _out61_hq(self):
        """Специальный режим Out61 (РЕТОМ-71) с гармониками"""
        self._ensure_com_initialized()
        try:
            logger.info(MODULE_NAME, "Starting Out61 high harmonics mode...")
            
            ch_main = self.retom.NewAnalogChannels()
            ch_main.dFrequency = self.signals["channel1"]["freq"]
            ch_main.SetSinSignal(0, self.signals["channel1"]["amplUA"], self.signals["channel1"]["anglUA"])    # Ua
            ch_main.SetSinSignal(1, self.signals["channel1"]["amplUB"], self.signals["channel1"]["anglUB"])    # Ub
            ch_main.SetSinSignal(2, self.signals["channel1"]["amplUC"], self.signals["channel1"]["anglUC"])    # Uc
            ch_main.SetSinSignal(3, self.signals["channel1"]["amplIA"], self.signals["channel1"]["anglIA"])    # Ia
            ch_main.SetSinSignal(4, self.signals["channel1"]["amplIB"], self.signals["channel1"]["anglIB"])    # Ib
            ch_main.SetSinSignal(5, self.signals["channel1"]["amplIC"], self.signals["channel1"]["anglIC"])    # Ic

            ch_main.AddHarmonica(3, self.signals["channel1"]["amplIA"], self.signals["channel1"]["anglIA"], 50, 0)
            ch_main.AddHarmonica(4, self.signals["channel1"]["amplIB"], self.signals["channel1"]["anglIB"], 50, 0)
            ch_main.AddHarmonica(5, self.signals["channel1"]["amplIC"], self.signals["channel1"]["anglIC"], 50, 0)

            ch_main.AddHarmonica(3, self.signals_hq["channel_hq"]["amplA2harm"], 0, 100, 0)
            ch_main.AddHarmonica(4, self.signals_hq["channel_hq"]["amplB2harm"], 240, 100, 0)
            ch_main.AddHarmonica(5, self.signals_hq["channel_hq"]["amplC2harm"], 120, 100, 0)

            ch_main.AddHarmonica(3, self.signals_hq["channel_hq"]["amplA5harm"], 0, 250, 0)
            ch_main.AddHarmonica(4, self.signals_hq["channel_hq"]["amplB5harm"], 240, 250, 0)
            ch_main.AddHarmonica(5, self.signals_hq["channel_hq"]["amplC5harm"], 120, 250, 0)

            ch_add = self.retom.NewAnalogChannels()
            ch_add.dFrequency = self.signals["channel2"]["freq"]
            ch_add.SetSinSignal(0, self.signals["channel2"]["amplUA"], self.signals["channel2"]["anglUA"])  # Ua2
            ch_add.SetSinSignal(1, self.signals["channel2"]["amplUB"], self.signals["channel2"]["anglUB"])  # Ub2
            ch_add.SetSinSignal(2, self.signals["channel2"]["amplUC"], self.signals["channel2"]["anglUC"])  # Uc2
            ch_add.SetSinSignal(3, self.signals["channel2"]["amplIA"], self.signals["channel2"]["anglIA"])  # Ia2
            ch_add.SetSinSignal(4, self.signals["channel2"]["amplIB"], self.signals["channel2"]["anglIB"])  # Ib2
            ch_add.SetSinSignal(5, self.signals["channel2"]["amplIC"], self.signals["channel2"]["anglIC"])  # Ic2

            mask = 0x00770077

            #self.retom.SetMaxUI(max(58, 58, 58) * 1.2, max(5, 5, 5) * 1.2)
            #self.retom.ChannelsReset()
            #time.sleep(1.0)

            result = self.retom.Out61(ch_main, mask, ch_add, mask)
            logger.info(MODULE_NAME, f"Out61_hq completed with result: {result}")
            return True
            
        except Exception as e:
            self.st_error = f"Out61_hq error: {e}"
            logger.error(MODULE_NAME, self.st_error)
            return False


    def _on_binary_inputs(self, nGroup, dwBinaryInput):
        """Callback для обработки события бинарных входов"""
        logger.info(MODULE_NAME, f"Binary Inputs Event - Group: {nGroup}, Value: {dwBinaryInput:016b}")
        
        if hasattr(self, 'external_binary_inputs_callback') and self.external_binary_inputs_callback:
            try:
                self.external_binary_inputs_callback(nGroup, dwBinaryInput)
            except Exception as e:
                logger.error(MODULE_NAME, f"Error in external callback: {e}")

    def set_binary_inputs_callback(self, callback):
        """Установка внешнего обработчика событий бинарных входов"""
        self.external_binary_inputs_callback = callback
        logger.info(MODULE_NAME, "Binary inputs callback set")


    def read_input_contacts(self, mode="mask"):
        """
        Read input contacts.
        
        Args:
            mode (str): Output format - "mask" (int), "list" (bool list), or "dict"
        
        Returns:
            Depending on mode:
                - "mask": 16-bit integer mask (In1 = bit 0, In16 = bit 15)
                - "list": List of 16 booleans [In1...In16]
                - "dict": Dictionary {"In1": bool, ..., "In16": bool}
                - None on error
        """
        self._ensure_com_initialized()
        
        if not self.retom:
            self.st_error = "Retom not initialized"
            logger.error(MODULE_NAME, self.st_error)
            return None
        
        try:
            import array
            byte_array = array.array('L', [0, 0])
            result = self.retom.ReadInputContacts(byte_array)

            # Debug logging (not print)
            logger.debug(MODULE_NAME, f"ReadInputContacts result: {result}")
            
            # Parse result based on the actual structure
            # Your COM method might return a tuple or the array directly
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                # Format: (data_array, hresult) or similar
                data = result[0]
            elif hasattr(result, '__len__') and len(result) >= 2:
                # Result might be the array itself
                data = result
            else:
                self.st_error = f"Unexpected result format: {type(result)}"
                return None
            
            # Extract bytes with proper order
            # data[0] = In9-In16 (high byte)
            # data[1] = In1-In8 (low byte)
            low_byte = int(data[1]) & 0xFF
            high_byte = int(data[0]) & 0xFF
            
            # Combine with byte swap (low byte becomes bits 0-7, high byte bits 8-15)
            final_mask = low_byte | (high_byte << 8)
            
            # Log active contacts
            active = [i+1 for i in range(16) if (final_mask >> i) & 1]
            logger.info(MODULE_NAME, 
                f"ReadInputContacts raw=[{high_byte}, {low_byte}] -> "
                f"mask=0x{final_mask:04X} ({final_mask}), active={active if active else 'none'}")
            
            # Return requested format
            if mode == "mask":
                return final_mask
            elif mode == "list":
                return [(final_mask >> i) & 1 for i in range(16)]
            elif mode == "dict":
                return {f"In{i+1}": bool((final_mask >> i) & 1) for i in range(16)}
            else:
                logger.warning(MODULE_NAME, f"Unknown mode '{mode}', returning mask")
                return final_mask
                
        except Exception as e:
            self.st_error = f"ReadInputContacts exception: {e}"
            logger.error(MODULE_NAME, self.st_error, exc_info=True)
            return None

    def remove_retom(self):
        """Перезапуск соединения с Retom"""
        process_killed = False
        recreation_success = False
        
        try:
            logger.info(MODULE_NAME, "Removing Retom...")
            
            self.message_pump_running = False
            self.unsubscribe_events()
            
            try:
                result = subprocess.run(['taskkill', '/F', '/IM', 'RTDI.exe'], 
                                    capture_output=True, 
                                    text=True,
                                    timeout=5)
                
                if result.returncode == 0:
                    process_killed = True
                    logger.info(MODULE_NAME, "RTDI.exe process killed successfully")
                    time.sleep(2)
                elif "not found" in result.stderr or "не найдена" in result.stderr:
                    process_killed = False
                    logger.warning(MODULE_NAME, "RTDI.exe process not found")
                else:
                    logger.warning(MODULE_NAME, f"Taskkill returned: {result.returncode}")
                    
            except subprocess.TimeoutExpired:
                logger.error(MODULE_NAME, "Taskkill timeout")
            except FileNotFoundError:
                logger.warning(MODULE_NAME, "taskkill command not found (not Windows?)")
            
            if process_killed or not self.is_open:
                if self.is_open and self.retom:
                    try:
                        self.retom.Close()
                        self.is_open = 0
                        logger.debug(MODULE_NAME, "Retom connection closed before recreation")                        
                    except Exception as e:
                        logger.warning(MODULE_NAME, f"Error closing before recreation: {e}")
                
                self.retom = None
                time.sleep(1)
                
                self.create_retom()
                self.st_function = "Open"
                recreation_success = self.run_retom()
            
            return recreation_success
            
        except Exception as ex:
            self.st_error = f"RemoveRetom failed: {ex}"
            logger.error(MODULE_NAME, self.st_error)
            return False