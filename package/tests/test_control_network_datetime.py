import datetime, unittest
from tvwcs import control_datetime as dt, control_network as net

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
    def test_finds_the_device_stanza_only(self):
        lines=INTERFACES.splitlines()
        self.assertEqual([lines[i] for i in net.ifupdown_lines(INTERFACES,"enp1s0")],["allow-hotplug enp1s0","iface enp1s0 inet dhcp"])
        self.assertEqual(net.ifupdown_lines(INTERFACES,"wlan0"),[])
    def test_takes_the_options_under_iface_too(self):
        text="auto eth0\niface eth0 inet static\n    address 10.0.0.2\n    gateway 10.0.0.1\n\niface lo inet loopback\n"
        self.assertEqual(net.ifupdown_lines(text,"eth0"),[0,1,2,3])
    def test_comments_the_device_out(self):
        out=net.without_device(INTERFACES,"enp1s0")
        self.assertIn(net.TAKEN_NOTE,out); self.assertIn("# allow-hotplug enp1s0\n# iface enp1s0 inet dhcp",out)
        self.assertIn("\nauto lo\niface lo inet loopback\n",out); self.assertEqual(net.ifupdown_lines(out,"enp1s0"),[])
    def test_auto_line_naming_others_keeps_them(self):
        out=net.without_device("auto lo eth0\niface eth0 inet dhcp\n","eth0")
        self.assertIn("# auto lo eth0\nauto lo\n",out)
    def test_network_manager_ignores_ifupdown(self):
        self.assertTrue(net.ifupdown_ignored(NM_CONF))
        self.assertFalse(net.ifupdown_ignored(NM_CONF.replace("managed=false","managed=true")))
        self.assertFalse(net.ifupdown_ignored("[main]\nplugins=keyfile\n"))

class SetTimeTests(unittest.TestCase):
    when=datetime.datetime(2026,1,31,23,59)
    def test_fields_wrap(self):
        self.assertEqual(dt.adjust(self.when,"minute",1).minute,0)
        self.assertEqual(dt.adjust(self.when,"hour",1).hour,0)
        self.assertEqual(dt.adjust(self.when,"day",1).day,1)
        self.assertEqual(dt.adjust(self.when,"month",1),datetime.datetime(2026,2,28,23,59))   # 31 Feb is 28 Feb
        self.assertEqual(dt.adjust(datetime.datetime(2028,2,29),"year",1),datetime.datetime(2029,2,28))
        self.assertEqual(dt.adjust(datetime.datetime(2099,5,1),"year",1).year,2099)
        with self.assertRaises(ValueError): dt.adjust(self.when,"second",1)
    def test_steps(self):
        self.assertEqual(dt.step(self.when,1),datetime.datetime(2026,2,1,0,0))
        self.assertEqual(dt.step(self.when,-1440).day,30)
    def test_digits(self):
        self.assertEqual(dt.from_digits(self.when,"1905"),datetime.datetime(2026,1,31,19,5))
        self.assertEqual(dt.from_digits(self.when,"705").hour,7)
        for bad in ("2460","19","abcd","12345"):
            with self.assertRaises(ValueError): dt.from_digits(self.when,bad)
    def test_set_time_command(self):
        self.assertEqual(dt.set_time_argv(datetime.datetime(2026,10,15,9,5,33)),["timedatectl","set-time","2026-10-15 09:05:00"])

if __name__=="__main__": unittest.main()
