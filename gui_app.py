import socket
import sys
import time

sys.dont_write_bytecode = True

import subprocess
import sys
import threading
import requests
import customtkinter as ctk
import webbrowser
from PIL import Image
import pystray
import os
from typing import Optional, Any
from bot.core import setup_logging

app_logger = setup_logging()


class ServerControlGUI:
    def __init__(self) -> None:
        self.root = ctk.CTk()
        self.root.title("Parser Server Control")
        self.root.geometry("400x700")
        self.root.resizable(False, False)

        self.server_process: Optional[threading.Thread] = None
        self.status_check_thread: Optional[threading.Thread] = None
        self.server: Optional[Any] = None
        self.running: bool = False
        self.tray_icon: Any = None
        self.is_in_tray: bool = False

        self.load_theme_settings()

        self.create_widgets()
        self.setup_tray()

    def load_theme_settings(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.icon_image = Image.new("RGB", (32, 32), "blue")

    def create_widgets(self) -> None:
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.title_label = ctk.CTkLabel(
            self.main_frame, text="Parser Server Control", font=("Roboto", 24, "bold")
        )
        self.title_label.pack(pady=20)

        self.theme_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.theme_frame.pack(pady=10)

        self.left_mode_label = ctk.CTkLabel(
            self.theme_frame,
            text="☀ ",
            font=("Segoe UI Emoji", 18),
            text_color="blue",
        )
        self.left_mode_label.pack(side="left", padx=5)

        self.theme_switch = ctk.CTkSwitch(
            self.theme_frame,
            text="",
            command=self.toggle_theme,
            onvalue="dark",
            offvalue="light",
            width=40,
            switch_width=40,
        )
        self.theme_switch.pack(side="left", padx=5)
        self.theme_switch.select()

        self.right_mode_label = ctk.CTkLabel(
            self.theme_frame,
            text="☾",
            font=("Segoe UI Emoji", 26),
            text_color="blue",
        )
        self.right_mode_label.pack(side="left", padx=5)

        self.create_status_section()
        self.create_control_buttons()
        self.create_server_link()
        self.create_progress_bar()
        self.create_log_section()

    def create_status_section(self) -> None:
        self.status_frame = ctk.CTkFrame(self.main_frame)
        self.status_frame.pack(pady=20, padx=20, fill="x")

        self.status_label = ctk.CTkLabel(
            self.status_frame, text="Server Status:", font=("Roboto", 14)
        )
        self.status_label.pack(side="left", padx=10)

        self.status_value = ctk.CTkLabel(
            self.status_frame,
            text="Stopped",
            font=("Roboto", 14, "bold"),
            text_color="red",
        )
        self.status_value.pack(side="left")

    def create_control_buttons(self) -> None:
        self.button_frame = ctk.CTkFrame(self.main_frame)
        self.button_frame.pack(pady=20)

        self.start_button = ctk.CTkButton(
            self.button_frame,
            text="Start Server",
            command=self.start_server,
            width=150,
            height=40,
            font=("Roboto", 14),
            fg_color="#28a745",
            hover_color="#218838",
        )
        self.start_button.pack(pady=10)

        self.stop_button = ctk.CTkButton(
            self.button_frame,
            text="Stop Server",
            command=self.stop_server,
            width=150,
            height=40,
            font=("Roboto", 14),
            fg_color="#dc3545",
            hover_color="#c82333",
            state="disabled",
        )
        self.stop_button.pack(pady=10)

        self.minimize_button = ctk.CTkButton(
            self.button_frame,
            text="Minimize to Tray",
            command=self.minimize_to_tray,
            width=150,
            height=40,
            font=("Roboto", 14),
            fg_color="#0066cc",
            hover_color="#0052a3",
        )
        self.minimize_button.pack(pady=10)

    def create_server_link(self) -> None:
        self.open_server_button = ctk.CTkButton(
            self.main_frame,
            text="Open Server Interface →",
            command=lambda: webbrowser.open("http://localhost:5000"),
            font=("Roboto", 12),
            fg_color="transparent",
            text_color=["#0066cc", "#4da6ff"],
            hover_color=["#f0f0f0", "#1f1f1f"],
            height=30,
        )
        self.open_server_button.pack(pady=5)
        self.open_server_button.pack_forget()

    def create_progress_bar(self) -> None:
        self.progress = ctk.CTkProgressBar(self.main_frame)
        self.progress.pack(pady=20, padx=20, fill="x")
        self.progress.set(0)

    def create_log_section(self) -> None:
        self.log_frame = ctk.CTkFrame(self.main_frame)
        self.log_frame.pack(pady=20, padx=20, fill="both", expand=True)

        self.log_label = ctk.CTkLabel(
            self.log_frame, text="Server Log", font=("Roboto", 12)
        )
        self.log_label.pack(pady=5)

        self.log_text = ctk.CTkTextbox(self.log_frame, height=150, font=("Roboto", 12))
        self.log_text.pack(padx=10, pady=5, fill="both", expand=True)

    def setup_tray(self) -> None:
        menu = (
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Exit", self.quit_application),
        )
        self.tray_icon = pystray.Icon(
            "server_control", self.icon_image, "Server Control", menu
        )

    def toggle_theme(self) -> None:
        new_mode = "dark" if self.theme_switch.get() == "dark" else "light"
        ctk.set_appearance_mode(new_mode)

    def start_server(self) -> None:
        if not self.running:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(("localhost", 5000))
                sock.close()
                self.start_server_thread()
            except socket.error:
                self.log_text.insert("end", "Error: Port 5000 is already in use!\n")
                self.log_text.insert(
                    "end", "Please check if another instance is running.\n"
                )
                app_logger.error("Port 5000 is already in use!")
                app_logger.error("Please check if another instance is running.")
                if sys.platform == "win32":
                    try:
                        netstat_result = subprocess.run(
                            ["netstat", "-ano"],
                            capture_output=True,
                            text=True,
                            shell=True,
                        )

                        pids = set()
                        for line in netstat_result.stdout.splitlines():
                            if ":5000" in line and "LISTENING" in line:
                                parts = line.strip().split()
                                pid = parts[-1]
                                pids.add(pid)

                        for pid in pids:
                            try:
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", pid],
                                    capture_output=True,
                                    shell=True,
                                    timeout=5,
                                )
                                self.log_text.insert(
                                    "end", f"Killed process with PID: {pid}\n"
                                )
                                app_logger.info(f"Killed process with PID: {pid}")
                                self.start_server_thread()
                            except subprocess.TimeoutExpired:
                                self.log_text.insert(
                                    "end", f"Timeout killing PID {pid}\n"
                                )
                                app_logger.error(f"Timeout killing PID {pid}")
                            except Exception as e:
                                self.log_text.insert(
                                    "end", f"Error killing PID {pid}: {e}\n"
                                )
                                app_logger.error(f"Error killing PID {pid}: {e}")
                    except Exception as e:
                        self.log_text.insert("end", f"Process check error: {e}\n")
                        app_logger.error(f"Process check error: {e}")
        self.log_text.see("end")

    def stop_server(self) -> None:
        if self.running:
            MAX_RETRIES = 3
            RETRY_DELAY = 1
            success = False

            for attempt in range(MAX_RETRIES):
                try:
                    self.log_text.insert(
                        "end",
                        f"Attempting to stop server (attempt {attempt + 1}/{MAX_RETRIES})...\n",
                    )
                    app_logger.info(f"Stop attempt {attempt + 1}/{MAX_RETRIES}")

                    if self.server:
                        self.server.shutdown()
                        success = True
                        self.log_text.insert(
                            "end", "Server received shutdown command\n"
                        )
                        app_logger.info("Server shutdown initiated")
                        break

                except Exception as e:
                    self.log_text.insert("end", f"Shutdown error: {str(e)}\n")
                    app_logger.error(f"Shutdown error: {str(e)}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)

            self.running = False
            self.server = None
            self.server_process = None

            port_freed = False
            for _ in range(5):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("localhost", 5000)) != 0:
                        port_freed = True
                        break
                time.sleep(0.5)

            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.status_value.configure(text="Stopped", text_color="red")
            self.progress.set(0)
            self.open_server_button.pack_forget()

            status_msg = "Server stopped" if success else "Server stop failed"
            self.log_text.insert(
                "end", f"{status_msg} | Port {'free' if port_freed else 'busy'}\n"
            )
            app_logger.info(f"Final stop status: {status_msg}")

    def monitor_server(self) -> None:
        import time
        from requests.exceptions import RequestException

        INITIAL_DELAY = 2
        POLL_INTERVAL = 2
        STATUS_ENDPOINT = "http://localhost:5000/api/server/status"

        self.log_text.insert("end", "Starting server monitoring...\n")
        app_logger.info("Starting server monitoring...")
        time.sleep(INITIAL_DELAY)

        status_checked = False

        while self.running and not status_checked:
            try:
                response = requests.get(
                    STATUS_ENDPOINT, timeout=5, headers={"Connection": "close"}
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "").lower()
                    timestamp = data.get("timestamp", "N/A")

                    def update_ui():
                        self.status_value.configure(
                            text=status.title(),
                            text_color="#28a745" if status == "running" else "orange",
                        )
                        self.progress.set(1)

                        if status == "running":
                            self.open_server_button.pack(
                                pady=5, after=self.button_frame
                            )
                            self.main_frame.update()
                        else:
                            self.open_server_button.pack_forget()

                        self.log_text.insert(
                            "end", f"Server status: {status} ({timestamp})\n"
                        )
                        app_logger.info(f"Server status: {status} ({timestamp})")
                        self.log_text.see("end")

                    self.root.after(0, update_ui)

                    if status == "running":
                        status_checked = True
                        self.log_text.insert("end", "Server started successfully!\n")
                        app_logger.info("Server started successfully!")

                else:
                    self.log_text.insert(
                        "end", f"Invalid response: {response.status_code}\n"
                    )
                    app_logger.error(f"Invalid response: {response.status_code}")

            except RequestException as e:
                self.log_text.insert("end", f"Connection error: {str(e)}\n")
                app_logger.error(f"Connection error: {str(e)}")

            except Exception as e:
                self.log_text.insert("end", f"Critical error: {str(e)}\n")
                app_logger.error(f"Critical error: {str(e)}")
                self.stop_server()
                break

            time.sleep(POLL_INTERVAL)

        if not status_checked and self.running:
            self.log_text.insert("end", "Failed to verify server status\n")
            app_logger.error("Failed to verify server status")
            self.stop_server()

    def minimize_to_tray(self) -> None:
        if not self.is_in_tray:
            self.root.withdraw()
            try:
                self.tray_icon = None
                menu = (
                    pystray.MenuItem("Show", self.show_window),
                    pystray.MenuItem("Exit", self.quit_application),
                )
                self.tray_icon = pystray.Icon(
                    "server_control", self.icon_image, "Server Control", menu
                )
                self.is_in_tray = True
                self.tray_icon.run()
            except Exception as e:
                self.log_text.insert("end", f"Tray error: {str(e)}\n")
                app_logger.error(f"Tray error: {str(e)}")
                self.root.deiconify()
                self.is_in_tray = False

    def show_window(self, icon: Any = None, item: Any = None) -> None:
        if icon:
            icon.stop()
        self.is_in_tray = False
        self.root.after(
            0,
            lambda: [
                self.root.deiconify(),
                self.root.lift(),
                self.root.focus_force(),
            ],
        )

    def quit_application(self, icon: Any = None, item: Any = None) -> None:
        if self.running:
            self.stop_server()
        if icon:
            icon.stop()
        self.is_in_tray = False
        self.root.after(0, self.root.destroy)

    def run(self) -> None:
        self.root.mainloop()

    def start_server_thread(self) -> None:
        if self.running:
            self.log_text.insert("end", "Server is already running\n")
            app_logger.warning("Server is already running")
            return

        from app import app

        def run_server() -> None:
            try:
                app_logger.info("=" * 50)
                app_logger.info("Starting Parser Server")
                app_logger.info("=" * 50)

                app_logger.info("Checking configuration...")
                app_logger.debug(f"Current directory: {os.getcwd()}")
                app_logger.debug(f"Python path: {sys.executable}")
                app_logger.debug(f"Python version: {sys.version}")

                app_logger.info("Starting server on http://localhost:5000")

                try:
                    from werkzeug.serving import make_server
                except ImportError:
                    app_logger.error("Werkzeug not installed")
                    self.log_text.insert("end", "Werkzeug not installed\n")
                    raise

                self.server = make_server("localhost", 5000, app)
                self.server.serve_forever()
            except Exception as e:
                app_logger.critical(f"Server startup failed: {str(e)}", exc_info=True)
                self.root.after(0, self.stop_server)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        self.server_process = server_thread

        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_value.configure(text="Starting...", text_color="orange")

        self.status_check_thread = threading.Thread(target=self.monitor_server)
        self.status_check_thread.daemon = True
        self.status_check_thread.start()


if __name__ == "__main__":
    app = ServerControlGUI()
    app.run()
