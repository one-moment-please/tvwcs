import unittest
from tvwcs import control_network as net

# /etc/network/interfaces as Debian's installer writes it (the HTPC's)
INTERFACES="""# This file describes the network interfaces available on your system
# and how to activate them. For more information, see interfaces(5).

source /etc/network/interfaces.d/*

# The loopback network interface
auto lo
iface lo inet loopback

# The primary network interface
allow-hotplug enp1s0
iface enp1s0 inet dhcp
"""
NM_CONF="[main]\nplugins=ifupdown,keyfile\n\n[ifupdown]\nmanaged=false\n"

class IfupdownTests(unittest.TestCase):
    def test_hand_over_uninstalls_ifupdown_and_removes_its_folder(self):
        argv=net.take_over_argv("wlp2s0","ifupdown")
        self.assertEqual(argv[:2],["sh","-c"]); self.assertEqual(argv[-1],"wlp2s0")
        self.assertIn("apt-get purge -y ifupdown",argv[2]); self.assertIn("rm -rf /etc/network\n",argv[2])
        self.assertIn("systemctl restart NetworkManager",argv[2])
        self.assertLess(argv[2].index("apt-get purge"),argv[2].index("rm -rf"))
        self.assertNotIn("apt-get",net.take_over_argv("enp1s0","config")[2])
        with self.assertRaises(ValueError): net.take_over_argv("wl;rm","ifupdown")
    def test_reason_is_ifupdown_only_where_network_manager_ignores_it(self):
        import os, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            conf=os.path.join(d,"nm.conf"); open(conf,"w").write(NM_CONF)
            ifaces=os.path.join(d,"interfaces"); open(ifaces,"w").write(INTERFACES); os.chmod(ifaces,0o600)
            with mock.patch.object(net,"NM_CONF",conf), mock.patch.object(net,"INTERFACES",ifaces), mock.patch.object(net,"have",lambda c:True):
                self.assertEqual(net.unmanaged_reason("wlp2s0"),"ifupdown")
                open(conf,"w").write("[main]\nplugins=keyfile\n")
                self.assertEqual(net.unmanaged_reason("wlp2s0"),"config")
    def test_network_manager_ignores_ifupdown(self):
        self.assertTrue(net.ifupdown_ignored(NM_CONF))
        self.assertFalse(net.ifupdown_ignored(NM_CONF.replace("managed=false","managed=true")))
        self.assertFalse(net.ifupdown_ignored("[main]\nplugins=keyfile\n"))

if __name__=="__main__": unittest.main()
