import socket
import os
import struct
from typing import Optional
from SecurityHandler import SecurityHandler  # Assume we have this implemented


class FileSender:
    def __init__(self, target_ip: str, port: int = 65432, chunk_size: int = 4096):
        """
        Initialize the file sender client
        Args:
            target_ip (str): IP address of the receiver device
            port (int): Port number for communication (default: 65432)
            chunk_size (int): File chunk size in bytes (default: 4096)
        """
        self.target_ip = target_ip
        self.port = port
        self.chunk_size = chunk_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.security_handler: Optional[SecurityHandler] = None

    def set_encryption(self, key: bytes):
        """Initialize encryption handler with provided key"""
        self.security_handler = SecurityHandler(key)

    def send_file(self, filename: str, progress_callback: Optional[callable] = None) -> bool:
        """
        Send a file to the target device
        Args:
            filename (str): Path to file to send
            progress_callback (callable): Optional function to track progress
        Returns:
            bool: True if transfer succeeded, False otherwise
        """
        try:
            with open(filename, 'rb') as file:
                # Connect to receiver
                self.sock.connect((self.target_ip, self.port))

                # Send metadata (filename, file size)
                file_size = os.path.getsize(filename)
                metadata = {
                    'filename': os.path.basename(filename),
                    'file_size': file_size,
                    'encrypted': self.security_handler is not None
                }
                self._send_metadata(metadata)

                # Send file chunks
                total_sent = 0
                for chunk in self._chunk_file(file):
                    if self.security_handler:
                        iv, ciphertext, tag = self.security_handler.encrypt_chunk(chunk)
                        # Pack encrypted data with verification tags
                        data = struct.pack('!I', len(iv)) + iv
                        data += struct.pack('!I', len(tag)) + tag
                        data += struct.pack('!I', len(ciphertext)) + ciphertext
                    else:
                        data = chunk

                    self.sock.sendall(data)
                    total_sent += len(chunk)

                    if progress_callback:
                        progress = int((total_sent / file_size) * 100)
                        progress_callback(progress)

                return True

        except FileNotFoundError:
            print(f"Error: File {filename} not found")
            return False
        except ConnectionRefusedError:
            print("Error: Connection refused by receiver")
            return False
        except Exception as e:
            print(f"Transfer failed: {str(e)}")
            return False
        finally:
            self.sock.close()

    def _send_metadata(self, metadata: dict):
        """Send file metadata using a structured header format"""
        header = {
            'filename': metadata['filename'].encode('utf-8'),
            'filename_len': len(metadata['filename']),
            'file_size': metadata['file_size'],
            'encrypted': metadata['encrypted']
        }

        # Pack header information
        header_format = f"!I{header['filename_len']}sQI"
        packed_header = struct.pack(
            header_format,
            header['filename_len'],
            header['filename'],
            header['file_size'],
            header['encrypted']
        )
        self.sock.sendall(packed_header)

    def _chunk_file(self, file_object):
        """Generator function to read file in chunks"""
        while True:
            chunk = file_object.read(self.chunk_size)
            if not chunk:
                break
            yield chunk

    def stop(self):
        """Close the socket connection"""
        if self.sock:
            self.sock.close()
            self.sock = None

    def __del__(self):
        """Destructor to ensure socket cleanup"""
        if self.sock:
            self.sock.close()