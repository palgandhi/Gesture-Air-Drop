import os
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
import struct


class SecurityHandler:
    def __init__(self, key: bytes = None):
        """
        Initialize cryptographic handler with optional key
        Args:
            key: 32-byte AES key (None generates random key)
        """
        self.key = key or os.urandom(32)
        self.backend = default_backend()

        if len(self.key) != 32:
            raise ValueError("Key must be 32 bytes for AES-256")

    def encrypt_chunk(self, plaintext: bytes) -> tuple:
        """
        Encrypt data chunk using AES-GCM
        Returns:
            (iv: bytes, ciphertext: bytes, tag: bytes)
        """
        # Generate random 96-bit IV
        iv = os.urandom(12)

        # Create cipher object
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv),
            backend=self.backend
        )
        encryptor = cipher.encryptor()

        # Encrypt and finalize to get tag
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        return (iv, ciphertext, encryptor.tag)

    def decrypt_chunk(self, iv: bytes, ciphertext: bytes, tag: bytes) -> bytes:
        """
        Decrypt AES-GCM encrypted chunk
        Returns:
            Decrypted plaintext bytes
        Raises:
            InvalidTag: If authentication fails
        """
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv, tag),
            backend=self.backend
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

    def pack_encrypted_chunk(self, iv: bytes, ciphertext: bytes, tag: bytes) -> bytes:
        """
        Package encrypted components for network transmission
        Format: [4-byte iv_len][iv][4-byte tag_len][tag][4-byte data_len][data]
        """
        return b''.join([
            struct.pack('!I', len(iv)), iv,
            struct.pack('!I', len(tag)), tag,
            struct.pack('!I', len(ciphertext)), ciphertext
        ])

    def unpack_encrypted_chunk(self, data: bytes) -> tuple:
        """
        Unpackage received encrypted data
        Returns:
            (iv, ciphertext, tag)
        """
        ptr = 0

        # Extract IV
        iv_len = struct.unpack_from('!I', data, ptr)[0]
        ptr += 4
        iv = data[ptr:ptr + iv_len]
        ptr += iv_len

        # Extract tag
        tag_len = struct.unpack_from('!I', data, ptr)[0]
        ptr += 4
        tag = data[ptr:ptr + tag_len]
        ptr += tag_len

        # Extract ciphertext
        data_len = struct.unpack_from('!I', data, ptr)[0]
        ptr += 4
        ciphertext = data[ptr:ptr + data_len]

        return iv, ciphertext, tag

    @staticmethod
    def generate_checksum(data: bytes) -> str:
        """
        Generate SHA-256 checksum for data integrity verification
        Returns:
            Hexadecimal digest string
        """
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def generate_key(cls) -> bytes:
        """Generate cryptographically secure random key"""
        return os.urandom(32)

    def get_key(self) -> bytes:
        """Retrieve current encryption key"""
        return self.key


# Usage Example
if __name__ == "__main__":
    # Test encryption/decryption cycle
    key = SecurityHandler.generate_key()
    handler = SecurityHandler(key)

    plaintext = b"Secret file content"

    # Encrypt
    iv, ciphertext, tag = handler.encrypt_chunk(plaintext)
    packed = handler.pack_encrypted_chunk(iv, ciphertext, tag)

    # Decrypt
    iv_unpacked, ciphertext_unpacked, tag_unpacked = handler.unpack_encrypted_chunk(packed)
    decrypted = handler.decrypt_chunk(iv_unpacked, ciphertext_unpacked, tag_unpacked)

    print("Original:", plaintext)
    print("Decrypted:", decrypted)
    print("Checksum:", SecurityHandler.generate_checksum(plaintext))