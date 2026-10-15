"""Power and sleep without a display: the idle times, what is due when, and reading xset, logind, pactl and
systemd-inhibit from saved samples."""
import os, tempfile, unittest

from tvwcs import power

XSET="""Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  600    cycle:  600
DPMS (Energy Star):
  Standby: 600    Suspend: 900    Off: 1200
  DPMS is Enabled
  Monitor is On
"""

class PowerTests(unittest.TestCase):
    def test_idle_option_is_cleaned(self):
        self.assertEqual(power.clean_idle(None),{"screen_off":None,"lock":0,"sleep":0})
        self.assertEqual(power.clean_idle({"screen_off":0,"lock":300,"sleep":"x"}),{"screen_off":0,"lock":300,"sleep":0})
        self.assertEqual(power.clean_idle({"lock":True,"sleep":-5})["lock"],0)
    def test_what_is_due_runs_once_per_idle_period_in_time_order(self):
        times={"screen_off":600,"lock":300,"sleep":1800}
        self.assertEqual(power.due(times,299,set()),[])
        self.assertEqual(power.due(times,700,set()),["lock","screen_off"])
        self.assertEqual(power.due(times,700,{"lock"}),["screen_off"])
        self.assertEqual(power.due({"screen_off":None,"lock":0,"sleep":60},120,set()),["sleep"])
    def test_durations(self):
        self.assertEqual([power.duration_text(v) for v in (0,60,300,3600,5400,7200)],["Never","1 minute","5 minutes","1 hour","90 minutes","2 hours"])
    def test_xset(self):
        x=power.parse_xset(XSET)
        self.assertEqual((x.saver,x.dpms,x.dpms_off),(600,True,600))
        off=power.parse_xset("timeout:  0    cycle:  600\nDPMS (Energy Star):\n  Standby: 0    Suspend: 0    Off: 0\n  DPMS is Disabled\n")
        self.assertEqual((off.saver,off.dpms,off.dpms_off),(0,False,0))
    def test_logind(self):
        l=power.parse_logind({"IdleAction":'s "suspend"',"IdleActionUSec":"t 1800000000","HandleLidSwitch":'s "suspend"'})
        self.assertEqual((l.available,l.idle_action,l.idle_seconds,l.lid),(True,"suspend",1800,"suspend"))
        self.assertFalse(power.parse_logind({}).available)

    def test_lid_only_where_there_is_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc,acpi=os.path.join(tmp,"lid"),os.path.join(tmp,"acpi")
            self.assertFalse(power.has_lid((proc,acpi)))                  # neither folder
            os.makedirs(proc); os.makedirs(os.path.join(acpi,"PNP0C0A:00"))
            self.assertFalse(power.has_lid((proc,acpi)))                  # a desktop: no lid button, a battery-less ACPI
            os.makedirs(os.path.join(acpi,"PNP0C0D:00")); self.assertTrue(power.has_lid((proc,acpi)))
            os.makedirs(os.path.join(proc,"LID0")); self.assertTrue(power.has_lid((proc,os.path.join(tmp,"none"))))

    def test_xss_lock_is_commented_out_of_the_i3_config(self):
        config="# i3 config\nexec --no-startup-id xss-lock --transfer-sleep-lock -- i3lock --nofork\n#exec xss-lock -- i3lock\nexec_always xss-lock -l -- i3lock\nexec --no-startup-id nm-applet\n"
        self.assertEqual(power.xss_lock_lines(config),[1,3])
        changed=power.without_xss_lock(config)
        self.assertEqual(power.xss_lock_lines(changed),[])
        self.assertIn("# exec --no-startup-id xss-lock --transfer-sleep-lock -- i3lock --nofork\n",changed)
        self.assertIn("exec --no-startup-id nm-applet\n",changed); self.assertEqual(changed.count(power.XSS_NOTE),2)
        with tempfile.TemporaryDirectory() as tmp:
            path=os.path.join(tmp,"config"); open(path,"w").write(config)
            env={"HOME":tmp,"XDG_CONFIG_HOME":os.path.join(tmp,"none")}
            self.assertIsNone(power.i3_config_path(env))
            os.makedirs(os.path.join(tmp,".i3")); os.rename(path,os.path.join(tmp,".i3","config")); path=power.i3_config_path(env)
            self.assertEqual(path,os.path.join(tmp,".i3","config"))
            self.assertEqual(power.stop_xss_lock(path),""); self.assertEqual(open(path).read(),changed)
            self.assertEqual(open(path+".before-tvwcs").read(),config)
            self.assertEqual(power.stop_xss_lock(path),""); self.assertEqual(open(path+".before-tvwcs").read(),config)   # the first copy is kept

    def test_xss_lock_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            for pid,name in (("1","systemd"),("42","i3"),("self","bash")):
                os.makedirs(os.path.join(tmp,pid)); open(os.path.join(tmp,pid,"comm"),"w").write(name+"\n")
            self.assertFalse(power.xss_lock_running(tmp))
            os.makedirs(os.path.join(tmp,"77")); open(os.path.join(tmp,"77","comm"),"w").write("xss-lock\n")
            self.assertTrue(power.xss_lock_running(tmp))
    def test_sound_and_inhibitors_keep_it_awake(self):
        self.assertTrue(power.parse_playing("Sink Input #12\n\tDriver: protocol-native.c\n\tCorked: no\n"))
        self.assertFalse(power.parse_playing("Sink Input #12\n\tCorked: yes\n"))
        text=("firefox 1000 tv 2345 firefox idle Playing video block\n"
              "NetworkManager 0 root 800 NetworkManager sleep NetworkManager needs to turn off networks delay\n")
        self.assertEqual(power.parse_inhibitors(text),["firefox"])
    def test_swayidle_command(self):
        argv=power.swayidle_argv({"screen_off":600,"lock":0,"sleep":1800},"/opt/tv wcs/bin/tvwcs")
        self.assertEqual(argv,["swayidle","-w","timeout","600","'/opt/tv wcs/bin/tvwcs' idle screen_off","resume","'/opt/tv wcs/bin/tvwcs' idle resume",
                               "timeout","1800","'/opt/tv wcs/bin/tvwcs' idle sleep"])
        self.assertIsNone(power.swayidle_argv({"screen_off":None,"lock":0,"sleep":0},"tvwcs"))

if __name__=="__main__": unittest.main()
