"""Power and sleep without a display: the idle times, what is due when, and reading xset, logind, pactl and
systemd-inhibit from saved samples."""
import unittest

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
