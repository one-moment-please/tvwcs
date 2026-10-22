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
            with mock.patch.object(net,"NM_CONF",conf), mock.patch.object(net,"INTERFACES",ifaces), mock.patch.object(net,"have",lambda c:True), \
                 mock.patch.object(net,"NETWORKD_RUN",d):   # not this computer's own (a CI runner's netplan uses systemd-networkd)
                self.assertEqual(net.unmanaged_reason("wlp2s0"),"ifupdown")
                open(conf,"w").write("[main]\nplugins=keyfile\n")
                self.assertEqual(net.unmanaged_reason("wlp2s0"),"config")
    def test_reason_is_netplan_where_it_gives_the_ports_to_networkd(self):
        import os, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            run=os.path.join(d,"network"); os.mkdir(run)
            with mock.patch.object(net,"NETWORKD_RUN",run), mock.patch.object(net,"INTERFACES",os.path.join(d,"none")), mock.patch.object(net,"have",lambda c:True):
                self.assertEqual(net.unmanaged_reason("enp1s0"),"config")
                open(os.path.join(run,"10-netplan-enp1s0.network"),"w").write("[Match]\nName=enp1s0\n")
                self.assertEqual(net.unmanaged_reason("enp1s0"),"netplan")
            with mock.patch.object(net,"NETWORKD_RUN",run), mock.patch.object(net,"INTERFACES",os.path.join(d,"none")), mock.patch.object(net,"have",lambda c:c!="netplan"):
                self.assertEqual(net.unmanaged_reason("enp1s0"),"config")
    def test_netplan_hand_over_sets_the_renderer_and_can_go_back(self):
        script=net.take_over_argv("enp1s0","netplan")[2]
        self.assertIn("renderer: NetworkManager\\n' > /etc/netplan/90-tvwcs-network-manager.yaml",script)
        self.assertIn("cp -a /etc/netplan/. \"$backup\"/",script)
        self.assertLess(script.index("netplan generate || undo"),script.index("netplan apply || undo"))
        self.assertNotIn("apt-get",script)
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
    def test_twelve_hour_clock(self):
        self.assertEqual(dt.hour_12(0),(12,False)); self.assertEqual(dt.hour_12(12),(12,True)); self.assertEqual(dt.hour_12(19),(7,True))
        self.assertEqual(dt.hour_24(12,False),0); self.assertEqual(dt.hour_24(12,True),12); self.assertEqual(dt.hour_24(7,True),19)
    def test_typed_fields(self):
        self.assertEqual(dt.from_fields("2026","10","16"," 9","05"),datetime.datetime(2026,10,16,9,5))
        self.assertEqual(dt.from_fields(2026,10,16,7,5,pm=True),datetime.datetime(2026,10,16,19,5))
        self.assertEqual(dt.from_fields(2026,10,16,12,0,pm=False).hour,0)
        for bad,why in (((2026,2,29,1,0),"between 1 and 28"),((2026,13,1,1,0),"month"),((1999,1,1,1,0),"year"),
                        ((2026,1,1,24,0),"hour"),((2026,1,1,1,60),"minute"),((2026,1,1,"",0),"number")):
            with self.assertRaises(ValueError) as e: dt.from_fields(*bad)
            self.assertIn(why,str(e.exception))
        with self.assertRaises(ValueError): dt.from_fields(2026,1,1,0,0,pm=True)   # 12-hour time has no hour 0
    def test_set_time_command(self):
        self.assertEqual(dt.set_time_argv(datetime.datetime(2026,10,15,9,5,33)),["timedatectl","set-time","2026-10-15 09:05:00"])

if __name__=="__main__": unittest.main()
