import time
import comtypes.client

RTDI_TLB = r".\RTDI\RTDI.tlb"
RTLINK_TLB = r".\RTDI\RTLink.tlb"

# --- Настройки ---
IP = "IP:192.168.11.146"
FREQ = 50.0
UA, UB, UC = 57.735, 57.735, 57.735
IA, IB, IC = 2.0, 2.0, 2.0
HOLD = 10.0  # секунд выдачи


def main():
    comtypes.client.GetModule(RTDI_TLB)
    comtypes.client.GetModule(RTLINK_TLB)
    from comtypes.gen import RTDI, RTLink

    retom = comtypes.client.CreateObject(RTDI.DualServer, interface=RTDI.IDualServer)
    time.sleep(3.0)

    try:
        retom.SetWorkParam("RetomType_66")

        for attempt in range(1, 6):
            if retom.Open(IP, 0):
                print(f"[OK] Подключено (попытка {attempt})")
                print(f"Номер устройства: {retom.ServerInfo.DeviceNumber}")
                print(f"Инфо: {retom.ServerInfo.Version}")
                
                break
            print(f"[...] Попытка {attempt} не удалась, повтор...")
            time.sleep(2)
        else:
            raise RuntimeError(f"Не удалось подключиться к РЕТОМ-71 по {IP}")

        try:
            retom.SetActivInputContact(0, 2)
        except Exception:
            pass

        # Основные каналы: Ua Ub Uc Ia Ib Ic
        ch_main = retom.NewAnalogChannels()
        ch_main.dFrequency = FREQ
        ch_main.SetSinSignal(0, UA, 0.0)    # Ua — фаза 0°
        ch_main.SetSinSignal(1, UB, 240.0)  # Ub — фаза 240°
        ch_main.SetSinSignal(2, UC, 120.0)  # Uc — фаза 120°
        ch_main.SetSinSignal(3, IA, 0.0)    # Ia — фаза 0°
        ch_main.SetSinSignal(4, IB, 240.0)  # Ib — фаза 240°
        ch_main.SetSinSignal(5, IC, 120.0)  # Ic — фаза 120°

        # Дополнительные каналы РЕТОМ-71: Ua2 Ub2 Uc2 Ia2 Ib2 Ic2
        ch_add = retom.NewAnalogChannels()
        ch_add.dFrequency = FREQ
        ch_add.SetSinSignal(0, 20.0, 0.0)   # Ua2
        ch_add.SetSinSignal(1, 20.0, 240.0) # Ub2
        ch_add.SetSinSignal(2, 20.0, 120.0) # Uc2
        ch_add.SetSinSignal(3, 0.0, 0.0)   # Ia2
        ch_add.SetSinSignal(4, 0.0, 240.0) # Ib2
        ch_add.SetSinSignal(5, 0.0, 120.0) # Ic2

        mask = 0x00770077

        retom.SetMaxUI(max(UA, UB, UC) * 1.2, max(IA, IB, IC) * 1.2)
        retom.ChannelsReset()
        time.sleep(1.0)

        result = retom.Out61(ch_main, mask, ch_add, mask)
        if not result:
            raise RuntimeError("Out61 вернул False — ошибка выдачи сигналов")
        print("[OK] Out61")

        retom.Enable()
        print(f"[OK] Enable — выдача {HOLD} сек...")
        time.sleep(HOLD)

        retom.Disable()
        print("[OK] Disable")

    finally:
        try:
            retom.Disable()
        except Exception:
            pass
        try:
            retom.Close()
            print("[OK] Close")
        except Exception:
            pass


if __name__ == "__main__":
    main()