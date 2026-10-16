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
        self.assertEqual(power.clean_idle(None),{"screensaver":0,"screen_off":None,"lock":0,"sleep":0})
        self.assertEqual(power.clean_idle({"screen_off":0,"lock":300,"sleep":"x"}),{"screensaver":0,"screen_off":0,"lock":300,"sleep":0})
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

    def test_xss_lock_can_use_the_tvwcs_lock_screen_and_go_back(self):
        config="# i3 config\nexec --no-startup-id xss-lock --transfer-sleep-lock -- i3lock --nofork\nexec --no-startup-id nm-applet\n"
        mine=power.with_xss_locker(config,"/opt/tvwcs/tvwcs lock --nofork")
        self.assertEqual(power.xss_lock_locker(mine),"/opt/tvwcs/tvwcs lock --nofork"); self.assertIn(power.XSS_LOCKER_NOTE+"i3lock --nofork\n",mine)
        self.assertEqual(power.with_xss_locker(mine,"/new/tvwcs lock --nofork").count(power.XSS_LOCKER_NOTE),1)   # moved install: still one note
        self.assertEqual(power.with_xss_locker(power.with_xss_locker(mine,"/new/tvwcs lock --nofork"),""),config)
        self.assertEqual(power.with_xss_locker(config,""),config)
        self.assertEqual(power.with_xss_locker("exec xss-lock\n","x"),"exec xss-lock\n")   # no locker given: left alone

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

    def test_xss_lock_fix_goes_to_tvwcs_session_config_in_its_own_session(self):
        """In TVWCS's own session (tvwcs-session exports TVWCS_SESSION), the config i3 runs with is TVWCS's, not the user's."""
        with tempfile.TemporaryDirectory() as tmp:
            usual=os.path.join(tmp,".config","i3","config"); os.makedirs(os.path.dirname(usual)); open(usual,"w").write("exec xss-lock -- i3lock\n")
            session=os.path.join(tmp,".config","tvwcs","i3-session.conf"); os.makedirs(os.path.dirname(session))
            env={"HOME":tmp}
            self.assertEqual(power.i3_config_path(env),usual)
            self.assertIsNone(power.i3_config_path({**env,"TVWCS_SESSION":"i3"}))   # never falls back to the usual one
            open(session,"w").write("exec xss-lock -- i3lock\n")
            self.assertEqual(power.i3_config_path({**env,"TVWCS_SESSION":"i3"}),session)
            other=os.path.join(tmp,"elsewhere.conf"); open(other,"w").write("")
            self.assertEqual(power.i3_config_path({**env,"TVWCS_SESSION":"i3","TVWCS_SESSION_CONFIG":other}),other)
            self.assertEqual(power.stop_xss_lock(power.i3_config_path({**env,"TVWCS_SESSION":"i3"})),"")
            self.assertEqual(open(usual).read(),"exec xss-lock -- i3lock\n"); self.assertIn("# exec xss-lock",open(session).read())
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
        self.assertIsNone(power.swayidle_argv({"screensaver":0,"screen_off":None,"lock":0,"sleep":0},"tvwcs"))

if __name__=="__main__": unittest.main()

class BatteryTests(unittest.TestCase):
    def supply(self, files):
        root=tempfile.mkdtemp()
        for name,values in files.items():
            os.makedirs(os.path.join(root,name))
            for k,v in values.items():
                with open(os.path.join(root,name,k),"w") as f: f.write(v+"\n")
        return root
    def test_no_battery(self):
        self.assertFalse(power.read_battery(self.supply({"AC":{"type":"Mains","online":"1"}})).present)
        self.assertFalse(power.read_battery("/nonexistent").present)
    def test_laptop_on_battery_and_plugged_in(self):
        b=power.read_battery(self.supply({"AC":{"type":"Mains","online":"0"},"BAT0":{"type":"Battery","status":"Discharging","energy_now":"30","energy_full":"60"}}))
        self.assertEqual((b.present,b.percent,b.on_battery),(True,50,True))
        b=power.read_battery(self.supply({"AC":{"type":"Mains","online":"1"},"BAT0":{"type":"Battery","status":"Charging","capacity":"77"}}))
        self.assertEqual((b.present,b.percent,b.on_battery),(True,77,False))
    def test_a_mouse_battery_is_not_the_computers(self):
        self.assertFalse(power.read_battery(self.supply({"hidpp_battery_0":{"type":"Battery","scope":"Device","capacity":"20","status":"Discharging"}})).present)
    def test_times_and_critical_action(self):
        settings={"idle":{"sleep":0},"idle_battery":{"sleep":600},"battery_critical":power.clean_critical(None)}
        low=power.Battery(True,4,True); plugged=power.Battery(True,4,False)
        self.assertEqual(power.active_idle(settings,low)["sleep"],600); self.assertEqual(power.active_idle(settings,plugged)["sleep"],0)
        self.assertEqual(power.critical(settings,low),"shutdown"); self.assertEqual(power.critical(settings,plugged),"")
        self.assertEqual(power.critical(settings,power.Battery(True,6,True)),"")
        settings["battery_critical"]=power.clean_critical({"action":"nothing","percent":90})
        self.assertEqual(power.critical(settings,low),"")
        self.assertEqual(power.clean_critical({"action":"explode","percent":0}),{"action":"shutdown","percent":5})
