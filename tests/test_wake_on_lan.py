import os
import unittest
from unittest.mock import patch

from tools.wake_on_lan import get_wol_configuration, wake_windows_pc


class TestWakeOnLan(unittest.TestCase):
    def test_configuration_reads_environment(self):
        with patch.dict(os.environ, {
            "WINDOWS_MAC_ADDRESS": "7C:10:C9:45:6A:40",
            "WINDOWS_WOL_BROADCAST": "192.168.100.255",
        }):
            self.assertEqual(get_wol_configuration(), {
                "mac": "7C:10:C9:45:6A:40",
                "broadcast": "192.168.100.255",
            })

    def test_invalid_mac_is_rejected(self):
        result = wake_windows_pc("not-a-mac")
        self.assertEqual(result["status"], "error")

    @patch("tools.wake_on_lan.socket.socket")
    def test_magic_packet_is_sent_three_times(self, socket_factory):
        socket_instance = socket_factory.return_value.__enter__.return_value
        result = wake_windows_pc("AA:BB:CC:DD:EE:FF", "192.168.1.255", 9)
        self.assertEqual(result["status"], "success")
        self.assertEqual(socket_instance.sendto.call_count, 3)
        packet, destination = socket_instance.sendto.call_args.args
        self.assertEqual(len(packet),  MagicPacketLength := 102)
        self.assertEqual(destination, ("192.168.1.255", 9))
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:12], bytes.fromhex("aabbccddeeff"))


if __name__ == "__main__":
    unittest.main()