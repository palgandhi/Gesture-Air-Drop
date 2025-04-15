import socket
import os
import struct
from typing import Optional
from SecurityHandler import SecurityHandler

class FileReceiver:
    def __init__(self, port: int = 65432, save_dir: str = "received_files"):
        self.port = port
        self.save_dir = save_dir
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn = None
        self.security_handler: Optional[SecurityHandler] = None
        self._create_save_dir()

    def _create_save_dir(self):
        os.makedirs(self.save_dir, exist_ok=True)

    def set_decryption(self, key: bytes):
        self.security_handler = SecurityHandler(key)

    def start(self):
        """Start listening for incoming connections"""
        self.sock.bind(('', self.port))
        self.sock.listen(1)
        print(f"Listening on port {self.port}...")

    def accept_connection(self):
        """Accept an incoming file transfer connection"""
        self.conn, addr = self.sock.accept()
        print(f"Connected to {addr}")

    def receive_file(self, progress_callback: Optional[callable] = None) -> str:
        """
        Receive and save the incoming file
        Returns:
            str: Path to the saved file
        """
        try:
            # Receive metadata
            header = self._receive_exact(4)
            filename_len = struct.unpack('!I', header)[0]

            filename = self._receive_exact(filename_len).decode()
            file_size = struct.unpack('!Q', self._receive_exact(8))[0]
            encrypted = bool(struct.unpack('!I', self._receive_exact(4))[0])

            save_path = os.path.join(self.save_dir, filename)
            total_received = 0

            with open(save_path, 'wb') as file:
                while total_received < file_size:
                    if encrypted:
                        # Read full encrypted chunk package
                        chunk_data = self._receive_exact(4)
                        iv_len = struct.unpack('!I', chunk_data)[0]
                        iv = self._receive_exact(iv_len)

                        chunk_data = self._receive_exact(4)
                        tag_len = struct.unpack('!I', chunk_data)[0]
                        tag = self._receive_exact(tag_len)

                        chunk_data = self._receive_exact(4)
                        data_len = struct.unpack('!I', chunk_data)[0]
                        ciphertext = self._receive_exact(data_len)

                        # Decrypt the chunk
                        plaintext = self.security_handler.decrypt_chunk(iv, ciphertext, tag)
                    else:
                        # Read plain chunk
                        plaintext = self.conn.recv(4096)

                    file.write(plaintext)
                    total_received += len(plaintext)

                    if progress_callback:
                        progress = min(100, int((total_received / file_size) * 100))
                        progress_callback(progress)

            return save_path

        except Exception as e:
            print(f"Reception failed: {str(e)}")
            return ""
        finally:
            self.conn.close()
            self.sock.close()

    def _receive_exact(self, num_bytes: int) -> bytes:
        """Helper to receive exact number of bytes"""
        data = bytearray()
        while len(data) < num_bytes:
            packet = self.conn.recv(num_bytes - len(data))
            if not packet:
                raise ConnectionError("Connection closed prematurely")
            data.extend(packet)
        return bytes(data)

# ---------------------------
# Example Usage (Test Script)
# ---------------------------
if __name__ == "__main__":
    # Test parameters (must match sender's)
    KEY = b'32-byte-secret-key-1234567890abc'  # Must match sender's key
    PORT = 65432

    # Create receiver
    receiver = FileReceiver(PORT)
    receiver.set_decryption(KEY)

    def progress(pct):
        print(f"Receiving: {pct}%")

    try:
        receiver.start()
        print("Waiting for sender...")
        receiver.accept_connection()

        saved_file = receiver.receive_file(progress)
        if saved_file:
            print(f"File saved to: {saved_file}")
            # Verify checksum if needed
        else:
            print("File reception failed")

    except KeyboardInterrupt:
        print("\nServer shutdown")
