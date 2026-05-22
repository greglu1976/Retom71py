
import time
import comtypes.client

from comtypes.gen import RTDI, RTLink

import subprocess

RTDI_TLB = r".\RTDI\RTDI.tlb"
RTLINK_TLB = r".\RTDI\RTLink.tlb"

IP = "IP:192.168.11.146"
FREQ = 50.0

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


    def create_retom(self):

        self.retom = comtypes.client.CreateObject(RTDI.DualServer, interface=RTDI.IDualServer)
        #self.retom = DualServer()
        time.sleep(3.0)


    def run_retom(self):

        self.st_result = ""
        if self.st_function == "Open":
            if self.retom == None:
                print("Ретом не инициализирован")
                return
            
            self.is_open = 0
            self.result_return = self.retom.close()
            try:
                self.result_return = self.retom.SetWorkParam("RetomType_66")

                self.is_open = self.retom.Open(IP, 0)
                if self.is_open == 1:
                    print(f"Номер устройства: {self.retom.ServerInfo.DeviceNumber}")
                    print(f"Версия ретом-мастера: {self.retom.ServerInfo.Version}")
                    return True
                else:
                    print("Устройство не подключено")
                    self.retom = None
                    self.st_error = "Failed to create DualServer instance"
                    return False
            except Exception as e:
                self.st_error = f"Error Create Retom: {e}"
                return False

        elif self.is_open > 0:
            match self.st_function:

                case "SetOutContact":
                    num_cont = 0
                    for value in self.contacts:
                        self.result_return = self.retom.SetOutContact(num_cont, value)
                        num_cont += 1
                    return True  
                                                 
                case "Close":
                    self.result_return = self.retom.Close()
                    self.is_open = 0
                    return True
                
                case "Enable":
                    self.result_return = self.retom.Enable()
                    return True
                
                case "Disable":
                    self.result_return = self.retom.Disable()
                    return True
                
                case "Out61":
                    # Основные каналы: Ua Ub Uc Ia Ib Ic
                    ch_main = self.retom.NewAnalogChannels()
                    ch_main.dFrequency = 50.0
                    ch_main.SetSinSignal(0, 0, 0.0)    # Ua — фаза 0°
                    ch_main.SetSinSignal(1, 0, 240.0)  # Ub — фаза 240°
                    ch_main.SetSinSignal(2, 0, 120.0)  # Uc — фаза 120°
                    ch_main.SetSinSignal(3, 1.0, 0.0)    # Ia — фаза 0°
                    ch_main.SetSinSignal(4, 1.0, 240.0)  # Ib — фаза 240°
                    ch_main.SetSinSignal(5, 1.0, 120.0)  # Ic — фаза 120°

                    # Дополнительные каналы РЕТОМ-71: Ua2 Ub2 Uc2 Ia2 Ib2 Ic2
                    ch_add = self.retom.NewAnalogChannels()
                    ch_add.dFrequency = 50.0
                    ch_add.SetSinSignal(0, 0.0, 0.0)   # Ua2
                    ch_add.SetSinSignal(1, 0.0, 240.0) # Ub2
                    ch_add.SetSinSignal(2, 0.0, 120.0) # Uc2
                    ch_add.SetSinSignal(3, 0.0, 0.0)   # Ia2
                    ch_add.SetSinSignal(4, 0.0, 240.0) # Ib2
                    ch_add.SetSinSignal(5, 0.0, 120.0) # Ic2

                    mask = 0x00770077

                    self.retom.SetMaxUI(max(58, 58, 58) * 1.2, max(5, 5,  5) * 1.2)
                    self.retom.ChannelsReset()
                    time.sleep(1.0)

                    result = self.retom.Out61(ch_main, mask, ch_add, mask)



                    return True
                case _:
                    return False
        return False


    def remove_retom(self):

        process_killed = False
        recreation_success = False
        try:
            # 1. Завершение процесса RTDI.exe
            try:
                # /F - принудительно, /IM - по имени образа
                result = subprocess.run(['taskkill', '/F', '/IM', 'RTDI.exe'], 
                                    capture_output=True, 
                                    text=True,
                                    timeout=5)
                
                if result.returncode == 0:
                    process_killed = True
                    print("RTDI.exe process killed successfully")
                    time.sleep(2)  # Даем время на завершение
                elif "not found" in result.stderr or "не найдена" in result.stderr:
                    # Процесс не был запущен
                    process_killed = False
                    print("RTDI.exe process not found")
                else:
                    print(f"Taskkill returned: {result.returncode}, stderr: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print("Taskkill timeout")
            except FileNotFoundError:
                print("taskkill command not found (not Windows?)")
            
            # 2. Пересоздание соединения
            if process_killed or not self.is_open:  # Всегда пытаемся пересоздать
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



retom = RetomDriver()
retom.create_retom()
retom.st_function = "Open"
retom.run_retom()
retom.st_function = "Enable"
retom.run_retom()

#retom.st_function = "Out61"
#retom.run_retom()

time.sleep(3.0)

retom.st_function = "Disable"
retom.run_retom()

retom.st_function = "Close"
retom.run_retom()