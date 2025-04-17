# menu_cli.py
import os
import sys
import time
import curses

from src.DeviceDiscovery import DeviceDiscovery
from src.FileReceiver import FileReceiver
from src.FileSender import FileSender
from src.SecurityHandler import SecurityHandler
from src.handDetection import HandDetector


class FileTransferCLI:
    def __init__(self, port=65432):
        self.port = port
        self.discovery = DeviceDiscovery(service_port=self.port)
        self.discovery.start_discovery()
        self.key_file = "encryption.key"
        self.key = self._load_key()

    def _load_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        return None

    def show_main_menu(self):
        

        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("=== HandAirDrop CLI ===")
            print("1. Send File")
            print("2. Receive Files")
            print("3. Generate Encryption Key")
            print("4. Exit")

            choice = input("\nSelect option: ")

            if choice == '1':
                self.send_file_flow()
            elif choice == '2':
                self.receive_file_flow()
            elif choice == '3':
                self.generate_key_flow()
            elif choice == '4':
                print("Goodbye!")
                self.discovery.stop_discovery()
                sys.exit()
            else:
                print("Invalid option, try again")
                time.sleep(1)

    def send_file_flow(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== Send File ===")

        # Device selection
        devices = self._wait_for_devices()
        if not devices:
            return

        target_ip = self._select_device(devices)
        if not target_ip:
            return

        # File selection
        file_path = input("\nEnter path to file: ").strip()
        if not os.path.exists(file_path):
            print("File does not exist!")
            time.sleep(1)
            return

        # Encryption check
        use_encryption = False
        if self.key:
            use_encryption = input("Use encryption? (y/n): ").lower() == 'y'

        # Send file
        sender = FileSender(target_ip, self.port)
        if use_encryption:
            sender.set_encryption(self.key)

        try:
            print("\nSending file...")
            if sender.send_file(file_path, self._progress_bar):
                print("\n✅ Transfer successful!")
            else:
                print("\n❌ Transfer failed")
        except Exception as e:
            print(f"\nError: {str(e)}")

        input("\nPress Enter to continue...")

    def receive_file_flow(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== Receive Files ===")
        print("Listening for incoming files...")
        print("Press Ctrl+C to stop listening\n")

        receiver = FileReceiver(self.port)
        if self.key:
            receiver.set_decryption(self.key)

        try:
            receiver.start()
            receiver.accept_connection()
            saved_path = receiver.receive_file(self._progress_bar)
            if saved_path:
                print(f"\n🎉 File saved to: {saved_path}")
            else:
                print("\n❌ Reception failed")
        except KeyboardInterrupt:
            print("\nStopped listening")
        except Exception as e:
            print(f"\nError: {str(e)}")

        input("Press Enter to continue...")

    def generate_key_flow(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== Generate Encryption Key ===")
        if os.path.exists(self.key_file):
            print("WARNING: This will overwrite existing key!")

        if input("Generate new key? (y/n): ").lower() == 'y':
            key = SecurityHandler.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            print(f"🔑 New key saved to {self.key_file}")
            self.key = key
            time.sleep(1)

    def _progress_bar(self, percentage):
        bars = int(percentage / 2)
        print(f"[{'#' * bars}{' ' * (50 - bars)}] {percentage}%", end='\r')

    def _wait_for_devices(self, timeout=25):
        print("Searching for devices...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            devices = self.discovery.get_available_devices()
            if devices:
                return devices
            print(".", end='', flush=True)
            time.sleep(1)

        print("\nNo devices found!")
        time.sleep(1)
        return None

    def _select_device(self, devices):
        print("\nAvailable devices:")
        for idx, (ip, name) in enumerate(devices, 1):
            print(f"{idx}. {name} ({ip})")
        print("0. Rescan devices")

        try:
            choice = int(input("\nSelect device: "))
            if choice == 0:
                return None
            return devices[choice - 1][0]
        except (ValueError, IndexError):
            print("Invalid selection!")
            time.sleep(1)
            return None


if __name__ == "__main__":
    try:
        cli = FileTransferCLI()
        cli.show_main_menu()
    except KeyboardInterrupt:
        print("\nApplication closed")