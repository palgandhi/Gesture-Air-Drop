# menu_cli.py - Complete Final Version
import os
import time
import cv2
import threading

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
        self.last_gesture = None
        self.status_message = "Ready"
        self.status_color = (0, 255, 0)  # Green

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
                self._update_status("Sender mode expired", (0, 0, 255))
                self.sender_mode = False
                self.detector.clear_selected_device()

            # Handle device selection timeout
            if self.device_selection_mode and (current_time - self.device_selection_start) > self.detector.device_selection_timeout:
                self._update_status("Device selection expired", (0, 0, 255))
                self.device_selection_mode = False
                self.detector.clear_selected_device()

            if lmList and len(lmList) >= 21:
                gesture = self.detector.detect_gesture(lmList)
                
                if gesture and (current_time - self.last_gesture_time) > self.gesture_cooldown:
                    self.last_gesture_time = current_time

                    if gesture == "Fist":
                        if not self.device_selection_mode:
                            # Start device selection
                            self.device_selection_mode = True
                            self.device_selection_start = current_time
                            self._update_status("Searching for devices...", (0, 255, 255))
                            
                            # Start device discovery in a separate thread
                            threading.Thread(target=self._discover_devices, daemon=True).start()
                        else:
                            self._update_status("Device already selected", (0, 255, 255))

                    elif gesture == "Palm":
                        if self.device_selection_mode and self.detector.is_device_selected():
                            # Device selected and palm shown - start file transfer
                            self._update_status("Starting file transfer", (0, 255, 0))
                            self.device_selection_mode = False
                            self.send_file_flow()
                        else:
                            self._update_status("No device selected", (0, 0, 255))

            # Display status
            self._draw_status(img)
            
            # Display instructions
            self._show_instructions(img)
            
            # Display gesture feedback
            if self.detector.current_gesture:
                self._draw_gesture_feedback(img)
            
            cv2.imshow("Gesture Control", img)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('1'):  # ESC or '1'
                break

        self.cleanup()

    def _update_status(self, message, color):
        """Update status message and color"""
        self.status_message = message
        self.status_color = color

    def _draw_status(self, img):
        """Draw status information on the image"""
        # Status box background
        cv2.rectangle(img, (10, 10), (300, 100), (0, 0, 0), -1)
        
        # Status text
        cv2.putText(img, f"Status: {self.status_message}", (20, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.status_color, 2)
        
        if self.device_selection_mode:
            remaining = int(self.detector.device_selection_timeout - 
                          (time.time() - self.device_selection_start))
            cv2.putText(img, f"Timeout in: {remaining}s", (20, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

    def _draw_gesture_feedback(self, img):
        """Draw gesture feedback on the image"""
        gesture = self.detector.current_gesture
        hold_time = time.time() - self.detector.gesture_start_time
        progress = min(1.0, hold_time / self.detector.gesture_hold_time)
        
        # Draw progress bar
        bar_width = 200
        bar_height = 20
        bar_x = img.shape[1] - bar_width - 20
        bar_y = 20
        
        cv2.rectangle(img, (bar_x, bar_y), 
                     (bar_x + bar_width, bar_y + bar_height), 
                     (100, 100, 100), -1)
        
        cv2.rectangle(img, (bar_x, bar_y), 
                     (bar_x + int(bar_width * progress), bar_y + bar_height), 
                     (0, 255, 0), -1)
        
        cv2.putText(img, f"{gesture}: {int(progress * 100)}%", 
                    (bar_x, bar_y + bar_height + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    def _show_instructions(self, img):
        """Draw instructions on the image"""
        instructions = [
            "Fist: Select Device",
            "Palm: Confirm Selection",
            "Press '1' or ESC to Exit"
        ]
        
        for i, text in enumerate(instructions):
            cv2.putText(img, text, (20, img.shape[0] - 30 - i * 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    def _discover_devices(self):
        """Discover available devices in a separate thread"""
        devices = self._wait_for_devices()
        if devices:
            # Automatically select the first available device
            target_ip = devices[0][0]
            self.detector.select_device(target_ip)
            self._update_status(f"Device selected: {target_ip}", (0, 255, 0))
        else:
            self._update_status("No devices found", (0, 0, 255))
            self.device_selection_mode = False

    def _wait_for_devices(self, timeout=25):
        """Wait for devices to be discovered"""
        print("Searching for devices...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            devices = self.discovery.get_available_devices()
            if devices:
                return devices
            time.sleep(0.5)

        return None

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

    def cleanup(self):
        self.cap.release()
        cv2.destroyAllWindows()
        self.discovery.stop_discovery()


if __name__ == "__main__":
    try:
        cli = FileTransferCLI()
        cli.show_main_menu()
    except KeyboardInterrupt:
        print("\nApplication closed")
    finally:
        if 'cli' in locals():
            cli.cleanup()