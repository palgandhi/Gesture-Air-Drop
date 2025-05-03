# menu_cli.py - Complete Final Version
import os
import time
import cv2
import threading
import socket
import glob

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
        
        # File transfer state
        self.standby_file = None
        self.standby_mode = False
        self.receiver_mode = False
        self.receiver_mode_start = 0
        self.receiver_mode_timeout = 10  # seconds
        
        # File selection state
        self.file_selection_mode = False
        self.available_files = []
        self.selected_file_index = 0
        self.file_selection_start = 0
        self.file_selection_timeout = 10  # seconds

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

            # Handle standby mode timeout
            if self.standby_mode and (current_time - self.sender_mode_start) > self.sender_mode_timeout:
                self._update_status("Standby mode expired", (0, 0, 255))
                self.standby_mode = False
                self.standby_file = None

            # Handle receiver mode timeout
            if self.receiver_mode and (current_time - self.receiver_mode_start) > self.receiver_mode_timeout:
                self._update_status("Receiver mode expired", (0, 0, 255))
                self.receiver_mode = False

            # Handle file selection timeout
            if self.file_selection_mode and (current_time - self.file_selection_start) > self.file_selection_timeout:
                self._update_status("File selection expired", (0, 0, 255))
                self.file_selection_mode = False
                self.available_files = []

            if lmList and len(lmList) >= 21:
                gesture = self.detector.detect_gesture(lmList)
                
                if gesture and (current_time - self.last_gesture_time) > self.gesture_cooldown:
                    self.last_gesture_time = current_time

                    if gesture == "Fist":
                        if not self.standby_mode and not self.receiver_mode and not self.file_selection_mode:
                            # Start file selection mode
                            self.file_selection_mode = True
                            self.file_selection_start = current_time
                            self._update_status("Select file to send", (0, 255, 255))
                            threading.Thread(target=self._prepare_files, daemon=True).start()
                        elif self.file_selection_mode and self.available_files:
                            # Select next file
                            self.selected_file_index = (self.selected_file_index + 1) % len(self.available_files)
                            self._update_status(f"Selected: {os.path.basename(self.available_files[self.selected_file_index])}", (0, 255, 255))
                        else:
                            self._update_status("No files available", (0, 0, 255))

                    elif gesture == "Palm":
                        if self.file_selection_mode and self.available_files:
                            # Confirm file selection
                            self.standby_file = self.available_files[self.selected_file_index]
                            self.standby_mode = True
                            self.sender_mode_start = current_time
                            self.file_selection_mode = False
                            self._update_status("File ready - Show Palm to send", (0, 255, 0))
                        elif not self.receiver_mode and not self.standby_mode:
                            # Start receiver mode
                            self.receiver_mode = True
                            self.receiver_mode_start = current_time
                            self._update_status("Ready to receive", (0, 255, 0))
                            threading.Thread(target=self._wait_for_sender, daemon=True).start()
                        elif self.standby_mode and self.standby_file:
                            # Send file to receiver
                            self._update_status("Sending file...", (0, 255, 0))
                            threading.Thread(target=self._send_file_to_receiver, daemon=True).start()
                        else:
                            self._update_status("No file selected", (0, 0, 255))

            # Display status
            self._draw_status(img)
            
            # Display instructions
            self._show_instructions(img)
            
            # Display gesture feedback
            if self.detector.current_gesture:
                self._draw_gesture_feedback(img)
            
            # Display file selection
            if self.file_selection_mode and self.available_files:
                self._draw_file_selection(img)
            
            cv2.imshow("Gesture Control", img)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('1'):  # ESC or '1'
                break

        self.cleanup()

    def _prepare_files(self):
        """Prepare list of available files"""
        # Get all files from Downloads and Desktop
        downloads = os.path.expanduser("~/Downloads")
        desktop = os.path.expanduser("~/Desktop")
        
        self.available_files = []
        for path in [downloads, desktop]:
            if os.path.exists(path):
                self.available_files.extend(glob.glob(os.path.join(path, "*")))
        
        # Filter out directories
        self.available_files = [f for f in self.available_files if os.path.isfile(f)]
        
        if not self.available_files:
            self._update_status("No files found", (0, 0, 255))
            self.file_selection_mode = False
            return
        
        self.selected_file_index = 0
        self._update_status(f"Selected: {os.path.basename(self.available_files[0])}", (0, 255, 255))

    def _wait_for_sender(self):
        """Wait for a sender to connect"""
        # Create a new socket for each attempt to avoid address in use error
        while self.receiver_mode:
            try:
                receiver = FileReceiver(self.port)
                if self.key:
                    receiver.set_decryption(self.key)

                receiver.start()
                self._update_status("Waiting for sender...", (0, 255, 255))
                receiver.accept_connection()
                saved_path = receiver.receive_file(self._progress_bar)
                if saved_path:
                    self._update_status("File received!", (0, 255, 0))
                    print(f"\n🎉 File saved to: {saved_path}")
                    break
                else:
                    self._update_status("Reception failed", (0, 0, 255))
            except Exception as e:
                if "Address already in use" in str(e):
                    # Try a different port
                    self.port += 1
                    continue
                self._update_status(f"Error: {str(e)}", (0, 0, 255))
            finally:
                if 'receiver' in locals():
                    receiver.stop()
        self.receiver_mode = False

    def _send_file_to_receiver(self):
        """Send file to waiting receiver"""
        if not self.standby_file:
            self._update_status("No file selected", (0, 0, 255))
            return

        devices = self._wait_for_devices()
        if not devices:
            self._update_status("No receivers found", (0, 0, 255))
            return

        # Find a device in receiver mode
        target_ip = None
        for ip, _ in devices:
            try:
                # Try to connect to check if device is in receiver mode
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect((ip, self.port))
                target_ip = ip
                sock.close()
                break
            except:
                continue

        if not target_ip:
            self._update_status("No receivers found", (0, 0, 255))
            return

        # Create a new sender for each attempt
        while True:
            try:
                sender = FileSender(target_ip, self.port)
                if self.key:
                    sender.set_encryption(self.key)

                if sender.send_file(self.standby_file, self._progress_bar):
                    self._update_status("Transfer successful!", (0, 255, 0))
                    break
                else:
                    self._update_status("Transfer failed", (0, 0, 255))
            except Exception as e:
                if "Address already in use" in str(e):
                    # Try a different port
                    self.port += 1
                    continue
                self._update_status(f"Error: {str(e)}", (0, 0, 255))
                break
            finally:
                if 'sender' in locals():
                    sender.stop()

        self.standby_mode = False
        self.standby_file = None

    def _draw_file_selection(self, img):
        """Draw file selection interface"""
        if not self.available_files:
            return

        # Draw file list background
        cv2.rectangle(img, (10, 120), (img.shape[1] - 10, 300), (0, 0, 0), -1)
        
        # Draw selected file
        selected_file = os.path.basename(self.available_files[self.selected_file_index])
        cv2.putText(img, f"Selected: {selected_file}", (20, 150), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw instructions
        cv2.putText(img, "Fist: Next file", (20, 180), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, "Palm: Confirm selection", (20, 210), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Draw timeout
        remaining = int(self.file_selection_timeout - 
                      (time.time() - self.file_selection_start))
        cv2.putText(img, f"Timeout in: {remaining}s", (20, 240), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

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
        
        if self.standby_mode:
            remaining = int(self.sender_mode_timeout - 
                          (time.time() - self.sender_mode_start))
            cv2.putText(img, f"Timeout in: {remaining}s", (20, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
        elif self.receiver_mode:
            remaining = int(self.receiver_mode_timeout - 
                          (time.time() - self.receiver_mode_start))
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
        if self.file_selection_mode:
            instructions = [
                "Fist: Next file",
                "Palm: Confirm selection",
                "Press '1' or ESC to Exit"
            ]
        elif self.standby_mode:
            instructions = [
                "Fist: File ready to send",
                "Palm: Send file to receiver",
                "Press '1' or ESC to Exit"
            ]
        elif self.receiver_mode:
            instructions = [
                "Palm: Ready to receive",
                "Waiting for sender...",
                "Press '1' or ESC to Exit"
            ]
        else:
            instructions = [
                "Fist: Select file to send",
                "Palm: Ready to receive",
                "Press '1' or ESC to Exit"
            ]
        
        for i, text in enumerate(instructions):
            cv2.putText(img, text, (20, img.shape[0] - 30 - i * 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    def _wait_for_devices(self, timeout=25):
        """Wait for devices to be discovered"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            devices = self.discovery.get_available_devices()
            if devices:
                return devices
            time.sleep(0.5)

        return None

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