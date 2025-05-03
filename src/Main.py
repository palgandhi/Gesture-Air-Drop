# menu_cli.py - Complete Final Version
import os
import time
import cv2

from DeviceDiscovery import DeviceDiscovery
from FileReceiver import FileReceiver
from FileSender import FileSender
from SecurityHandler import SecurityHandler
from handDetection import HandDetector


class FileTransferCLI:
    def __init__(self, port=65432):
        self.port = port
        self.discovery = DeviceDiscovery(service_port=self.port)
        self.discovery.start_discovery()
        self.key_file = "encryption.key"
        self.key = self._load_key()
        self.detector = HandDetector()
        
        # Gesture control state
        self.last_gesture_time = 0
        self.gesture_cooldown = 1.5  # seconds between gesture detections
        self.sender_mode = False
        self.sender_mode_timeout = 10  # seconds
        self.sender_mode_start = 0
        self.device_selection_mode = False
        self.device_selection_start = 0

    def _load_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        return None
    
    def show_main_menu(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("Error: Could not open camera.")
            return

        while True:
            success, img = self.cap.read()
            if not success:
                print("Failed to grab frame.")
                continue

            img = self.detector.find_hands(img)
            lmList = self.detector.find_position(img)
            current_time = time.time()

            # Handle sender mode timeout
            if self.sender_mode and (current_time - self.sender_mode_start) > self.sender_mode_timeout:
                self._show_feedback(img, "Sender mode expired")
                self.sender_mode = False
                self.detector.clear_selected_device()

            # Handle device selection timeout
            if self.device_selection_mode and (current_time - self.device_selection_start) > self.detector.device_selection_timeout:
                self._show_feedback(img, "Device selection expired")
                self.device_selection_mode = False
                self.detector.clear_selected_device()

            if lmList and len(lmList) >= 21:
                gesture = self.detector.is_palm_or_fist(lmList)
                
                if gesture and (current_time - self.last_gesture_time) > self.gesture_cooldown:
                    self.last_gesture_time = current_time

                    if gesture == "Fist":
                        print(f"Gesture detected: {gesture}")
                        if not self.device_selection_mode:
                            # Start device selection
                            self.device_selection_mode = True
                            self.device_selection_start = current_time
                            self._show_feedback(img, "Select device - show Palm to confirm")
                            devices = self._wait_for_devices()
                            if devices:
                                target_ip = self._select_device(devices)
                                if target_ip:
                                    self.detector.select_device(target_ip)
                                    self._show_feedback(img, f"Device selected: {target_ip}")
                        else:
                            # Already in device selection mode, show feedback
                            self._show_feedback(img, "Device already selected")

                    elif gesture == "Palm":
                        print(f"Gesture detected: {gesture}")
                        if self.device_selection_mode and self.detector.is_device_selected():
                            # Device selected and palm shown - start file transfer
                            self._show_feedback(img, "Starting file transfer")
                            self.device_selection_mode = False
                            self.send_file_flow()
                        else:
                            self._show_feedback(img, "No device selected")

            # Display status
            status_text = "Device Selection" if self.device_selection_mode else "Ready"
            status_color = (0, 255, 255) if self.device_selection_mode else (0, 255, 0)
            cv2.putText(img, f"Status: {status_text}", (50, 150), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

            if self.device_selection_mode:
                remaining = int(self.detector.device_selection_timeout - (current_time - self.device_selection_start))
                cv2.putText(img, f"Timeout in: {remaining}s", (50, 180), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

            # Display instructions
            self._show_instructions(img)
            cv2.imshow("Gesture Control", img)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('1'):  # ESC or '1'
                break

        self.cleanup()

    def _show_instructions(self, img):
        cv2.putText(img, "Fist: Select Device", (50, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(img, "Palm: Confirm Selection", (50, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(img, "Press '1' or ESC to Exit", (50, 110), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    def _show_feedback(self, img, message):
        cv2.putText(img, message, (img.shape[1]//2 - 100, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("Gesture Control", img)
        cv2.waitKey(500)

    def cleanup(self):
        self.cap.release()
        cv2.destroyAllWindows()
        self.discovery.stop_discovery()

    def send_file_flow(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== Send File ===")

        target_ip = self.detector.get_selected_device()
        if not target_ip:
            print("No device selected!")
            time.sleep(1)
            return

        file_path = input("\nEnter path to file: ").strip()
        if not os.path.exists(file_path):
            print("File does not exist!")
            time.sleep(1)
            return

        use_encryption = False
        if self.key:
            use_encryption = input("Use encryption? (y/n): ").lower() == 'y'

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
        self.detector.clear_selected_device()

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
    finally:
        if 'cli' in locals():
            cli.cleanup()