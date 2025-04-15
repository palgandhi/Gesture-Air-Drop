# ------------ File: device_discovery.py ------------
import socket
import threading
import time
from typing import Dict, List, Tuple
import pickle


class DeviceDiscovery:
    def __init__(self, service_port: int = 65432, discovery_port: int = 65433):
        """
        Initialize device discovery service
        Args:
            service_port: Main service port for file transfers
            discovery_port: Port used for discovery broadcasts
        """
        self.service_port = service_port
        self.discovery_port = discovery_port
        self.devices: Dict[str, Tuple[str, str]] = {}  # {ip: (name, last_seen)}
        self.running = False
        self.listener_thread: threading.Thread = None
        self.broadcaster_thread: threading.Thread = None
        self.device_name = socket.gethostname()
        self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start_discovery(self, broadcast_interval: int = 5):
        """
        Start device discovery service
        Args:
            broadcast_interval: Seconds between presence broadcasts
        """
        self.running = True

        # Start listener thread
        self.listener_thread = threading.Thread(target=self._listen_for_devices)
        self.listener_thread.daemon = True
        self.listener_thread.start()

        # Start broadcaster thread
        self.broadcaster_thread = threading.Thread(
            target=self._broadcast_presence,
            args=(broadcast_interval,)
        )
        self.broadcaster_thread.daemon = True
        self.broadcaster_thread.start()

    def stop_discovery(self):
        """Stop all discovery activities"""
        self.running = False
        if self.discovery_socket:
            self.discovery_socket.close()

    def get_available_devices(self) -> List[Tuple[str, str]]:
        """Return list of (ip, name) for recent devices"""
        self._prune_old_devices()
        return [(ip, data[0]) for ip, data in self.devices.items()]

    def _broadcast_presence(self, interval: int):
        """Broadcast device presence at regular intervals"""
        message = pickle.dumps({
            'name': self.device_name,
            'port': self.service_port
        })

        while self.running:
            try:
                self.discovery_socket.sendto(
                    message,
                    ('<broadcast>', self.discovery_port)
                )
                time.sleep(interval)
            except Exception as e:
                print(f"Broadcast error: {e}")
                break

    def _listen_for_devices(self):
        """Listen for incoming device broadcasts"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('', self.discovery_port))

            while self.running:
                try:
                    data, addr = listener.recvfrom(1024)
                    device_info = pickle.loads(data)
                    ip = addr[0]

                    if ip != self._get_local_ip():
                        self.devices[ip] = (
                            device_info['name'],
                            time.time()
                        )
                except (pickle.PickleError, KeyError):
                    continue
                except Exception as e:
                    print(f"Discovery error: {e}")
                    break

    def _prune_old_devices(self, timeout: int = 30):
        """Remove devices not seen recently"""
        current_time = time.time()
        expired = [ip for ip, data in self.devices.items()
                   if current_time - data[1] > timeout]
        for ip in expired:
            del self.devices[ip]

    @staticmethod
    def _get_local_ip() -> str:
        """Get primary local IP address"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


# ---------------------------
# Example Usage
# ---------------------------
if __name__ == "__main__":
    discovery = DeviceDiscovery()


    def print_devices():
        while True:
            devices = discovery.get_available_devices()
            print("\nAvailable devices:")
            for ip, name in devices:
                print(f" - {name} ({ip})")
            time.sleep(5)


    discovery.start_discovery()
    print("Starting discovery service...")

    try:
        print_devices()
    except KeyboardInterrupt:
        discovery.stop_discovery()
        print("\nDiscovery service stopped")