"""
ECblue Basic — адресатор
Подключение через MOXA UPort 1150 (RS-485 / Modbus RTU)
Автор: Ivan | Оборудование: ZIEHL-ABEGG ECblue Basic
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial.tools.list_ports

try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    from pymodbus.client.serial import ModbusSerialClient

DEFAULT_SLAVE   = 247
REG_PIN         = 0
REG_COM_PARAM   = 3
PIN_LEVEL2      = 10
PIN_APPLY       = 3698
BAUD            = 19200
PARITY          = 'E'
STOPBITS        = 1
POLL_INTERVAL   = 2.0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ECblue Basic — Изменение адреса")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")
        self.client      = None
        self.connected   = False
        self.running     = True
        self._build_ui()
        self._refresh_ports()
        self.monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self.monitor_thread.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        PAD = dict(padx=14, pady=6)
        frm_conn = tk.Frame(self, bg="#f0f0f0")
        frm_conn.pack(fill="x", **PAD)
        tk.Label(frm_conn, text="COM-порт:", bg="#f0f0f0").pack(side="left")
        self.port_var = tk.StringVar()
        self.cb_port = ttk.Combobox(frm_conn, textvariable=self.port_var, width=12, state="readonly")
        self.cb_port.pack(side="left", padx=(4, 8))
        self.btn_refresh = tk.Button(frm_conn, text="⟳", width=3, command=self._refresh_ports)
        self.btn_refresh.pack(side="left")
        self.lbl_status = tk.Label(self, text="● Нет связи",
                                   fg="#cc0000", bg="#f0f0f0", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(**PAD)
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=14)
        frm_cur = tk.Frame(self, bg="#f0f0f0")
        frm_cur.pack(fill="x", **PAD)
        tk.Label(frm_cur, text="Текущий адрес:", bg="#f0f0f0", font=("Segoe UI", 10)).pack(side="left")
        self.lbl_addr = tk.Label(frm_cur, text="—", font=("Segoe UI", 22, "bold"), fg="#1a5276", bg="#f0f0f0")
        self.lbl_addr.pack(side="left", padx=12)
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=14)
        frm_new = tk.Frame(self, bg="#f0f0f0")
        frm_new.pack(fill="x", **PAD)
        tk.Label(frm_new, text="Новый адрес (1–246):", bg="#f0f0f0", font=("Segoe UI", 10)).pack(side="left")
        vcmd = (self.register(self._validate_addr), '%P')
        self.entry_new = tk.Entry(frm_new, width=6, justify="center", font=("Segoe UI", 13),
                                  validate="key", validatecommand=vcmd)
        self.entry_new.pack(side="left", padx=8)
        self.btn_write = tk.Button(frm_new, text="Записать адрес",
                                   font=("Segoe UI", 10), bg="#1a5276", fg="white",
                                   activebackground="#154360", relief="flat", padx=10,
                                   command=self._write_address, state="disabled")
        self.btn_write.pack(side="left")
        self.lbl_log = tk.Label(self, text="", bg="#f0f0f0", fg="#555", font=("Segoe UI", 9), wraplength=340)
        self.lbl_log.pack(**PAD)

    def _validate_addr(self, value):
        if value == "": return True
        if value.isdigit() and 1 <= int(value) <= 246: return True
        if value.isdigit() and len(value) <= 3: return True
        return False

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.cb_port["values"] = ports
        if ports: self.cb_port.current(0)

    def _connect(self, port):
        if self.client:
            try: self.client.close()
            except Exception: pass
        self.client = ModbusSerialClient(
            port=port, baudrate=BAUD, parity=PARITY,
            stopbits=STOPBITS, bytesize=8, timeout=1)
        return self.client.connect()

    def _auth_and_read(self):
        wr = self.client.write_register(REG_PIN, PIN_LEVEL2, slave=DEFAULT_SLAVE)
        if wr.isError(): return None
        time.sleep(0.1)
        rr = self.client.read_holding_registers(REG_COM_PARAM, 1, slave=DEFAULT_SLAVE)
        if rr.isError() or not hasattr(rr, "registers"): return None
        val = rr.registers[0]
        return (val >> 8) & 0xFF, val

    def _do_write(self, new_addr, current_h3):
        new_val = (new_addr << 8) | (current_h3 & 0x00FF)
        wr = self.client.write_register(REG_COM_PARAM, new_val, slave=DEFAULT_SLAVE)
        if wr.isError(): return False
        time.sleep(0.1)
        self.client.write_register(REG_PIN, PIN_APPLY, slave=DEFAULT_SLAVE)
        return True

    def _monitor(self):
        last_port = None
        while self.running:
            port = self.port_var.get()
            if not port:
                time.sleep(POLL_INTERVAL)
                continue
            if not self.connected or port != last_port:
                ok = False
                try: ok = self._connect(port)
                except Exception: pass
                if ok:
                    result = None
                    try: result = self._auth_and_read()
                    except Exception: pass
                    if result:
                        addr, h3_val = result
                        self._h3_cache = h3_val
                        self.connected = True
                        last_port = port
                        self.after(0, self._set_connected, addr)
                    else:
                        self.connected = False
                        self.after(0, self._set_disconnected)
                else:
                    self.connected = False
                    self.after(0, self._set_disconnected)
            else:
                try:
                    rr = self.client.read_holding_registers(REG_COM_PARAM, 1, slave=DEFAULT_SLAVE)
                    if rr.isError() or not hasattr(rr, "registers"): raise Exception()
                except Exception:
                    self.connected = False
                    self.after(0, self._set_disconnected, "Устройство отключено. Ожидаю подключения…")
            time.sleep(POLL_INTERVAL)

    def _set_connected(self, addr):
        self.lbl_status.config(text="● Связь установлена", fg="#1e8449")
        self.lbl_addr.config(text=str(addr))
        self.btn_write.config(state="normal")
        self._log("Авторизация выполнена. Адрес прочитан.")

    def _set_disconnected(self, msg="Нет связи"):
        self.lbl_status.config(text=f"● {msg}", fg="#cc0000")
        self.lbl_addr.config(text="—")
        self.btn_write.config(state="disabled")
        self._log(msg)

    def _log(self, text):
        self.lbl_log.config(text=text)

    def _write_address(self):
        raw = self.entry_new.get().strip()
        if not raw or not raw.isdigit():
            messagebox.showwarning("Ошибка", "Введите адрес от 1 до 246.")
            return
        new_addr = int(raw)
        if not (1 <= new_addr <= 246):
            messagebox.showwarning("Ошибка", "Адрес должен быть от 1 до 246.")
            return
        if not self.connected:
            messagebox.showwarning("Ошибка", "Нет связи с устройством.")
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Изменить адрес на {new_addr}?\n\nПосле записи устройство применит новый адрес."):
            return
        def do_write():
            try:
                self.client.write_register(REG_PIN, PIN_LEVEL2, slave=DEFAULT_SLAVE)
                time.sleep(0.1)
                ok = self._do_write(new_addr, self._h3_cache)
                if ok:
                    self._h3_cache = (new_addr << 8) | (self._h3_cache & 0x00FF)
                    self.after(0, self.lbl_addr.config, {"text": str(new_addr)})
                    self.after(0, self._log, f"✓ Адрес изменён на {new_addr}. Подключите следующее устройство.")
                    self.after(0, self.entry_new.delete, 0, tk.END)
                    self.connected = False
                    self.after(0, self._set_disconnected, "Отключите устройство и подключите следующее.")
                else:
                    self.after(0, messagebox.showerror, "Ошибка", "Не удалось записать адрес.")
            except Exception as e:
                self.after(0, messagebox.showerror, "Ошибка", str(e))
        threading.Thread(target=do_write, daemon=True).start()

    def _on_close(self):
        self.running = False
        if self.client:
            try: self.client.close()
            except Exception: pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()