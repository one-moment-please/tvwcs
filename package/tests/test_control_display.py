"""The Settings app's Displays page without a display: xrandr and swaymsg output parsed from saved samples, the
arrangement kept when a resolution changes, the commands it would run, and the settings saved for the next login."""
import json, tempfile, unittest
from pathlib import Path

from tvwcs import control_display as disp

XRANDR="""Screen 0: minimum 320 x 200, current 4480 x 1440, maximum 16384 x 16384
HDMI-1 connected primary 1920x1080+0+180 (normal left inverted right x axis y axis) 527mm x 296mm
   1920x1080     60.00*+  50.00    59.94
   1920x1080i    60.00    50.00
   1280x720      60.00    59.94    50.00
   1024x768      60.00
DP-1 connected 2560x1440+1920+0 (normal left inverted right x axis y axis) 597mm x 336mm
   2560x1440     59.95 + 143.97*
   1920x1080     60.00    59.94
DP-2 disconnected (normal left inverted right x axis y axis)
VGA-1 connected (normal left inverted right x axis y axis)
   1024x768      60.00 +
   800x600       60.32    56.25
"""
ROTATED="""Screen 0: minimum 320 x 200, current 1080 x 1920, maximum 16384 x 16384
HDMI-1 connected primary 1080x1920+0+0 left (normal left inverted right x axis y axis) 527mm x 296mm
   1920x1080     60.00*+
"""
SWAY=json.dumps([
    {"name":"HDMI-A-1","make":"Samsung Electric Company","model":"QN55","active":True,"scale":2.0,"transform":"normal",
     "rect":{"x":0,"y":0,"width":1920,"height":1080},"current_mode":{"width":3840,"height":2160,"refresh":60000},
     "modes":[{"width":3840,"height":2160,"refresh":60000},{"width":3840,"height":2160,"refresh":30000},{"width":1920,"height":1080,"refresh":60000}]},
    {"name":"eDP-1","make":"Unknown","model":"Unknown","active":False,"rect":{"x":0,"y":0,"width":0,"height":0},
     "modes":[{"width":1366,"height":768,"refresh":60059}]},
])

def outputs(text=XRANDR): return disp.parse_xrandr(text)
def by(outs, name): return next(o for o in outs if o.name==name)

class ParseTests(unittest.TestCase):
    def test_xrandr_outputs_modes_and_rates(self):
        outs=outputs()
        self.assertEqual([o.name for o in outs],["HDMI-1","DP-1","VGA-1"])   # the disconnected DP-2 is left out
        hdmi,dp,vga=outs
        self.assertTrue(hdmi.primary and hdmi.enabled); self.assertEqual((hdmi.x,hdmi.y,hdmi.width,hdmi.height,hdmi.rate),(0,180,1920,1080,60.0))
        self.assertEqual([(m.width,m.height,m.interlaced) for m in hdmi.modes],[(1920,1080,False),(1920,1080,True),(1280,720,False),(1024,768,False)])
        self.assertEqual(hdmi.modes[0].rates,[60.0,59.94,50.0]); self.assertTrue(hdmi.modes[0].preferred)
        self.assertEqual((dp.rate,dp.x),(143.97,1920)); self.assertTrue(dp.modes[0].preferred); self.assertFalse(dp.primary)
        self.assertFalse(vga.enabled); self.assertEqual(vga.preferred_mode().width,1024)   # connected, switched off
    def test_xrandr_rotated_display_covers_its_turned_size(self):
        o,=outputs(ROTATED)
        self.assertTrue(o.rotated); self.assertEqual((o.width,o.height),(1920,1080)); self.assertEqual(o.size,(1080,1920))
    def test_sway_outputs(self):
        tv,laptop=disp.parse_sway(SWAY)
        self.assertEqual((tv.label,tv.width,tv.height,tv.rate,tv.size),("Samsung Electric Company QN55",3840,2160,60.0,(1920,1080)))
        self.assertEqual(tv.modes[0].rates,[60.0,30.0]); self.assertTrue(tv.modes[0].preferred)
        self.assertEqual(laptop.label,""); self.assertFalse(laptop.enabled); self.assertEqual(laptop.modes[0].rates,[60.059])
        self.assertEqual(disp.parse_sway("not json"),[])
    def test_texts(self):
        self.assertEqual(disp.rate_text(60.0),"60 Hz"); self.assertEqual(disp.rate_text(59.94),"59.94 Hz"); self.assertEqual(disp.rate_text(143.97),"143.97 Hz")
        self.assertEqual(disp.mode_text(disp.Mode(1920,1080,True)),"1920 × 1080 (interlaced)")
    def test_backend(self):
        yes=lambda _n:True
        self.assertEqual(disp.backend({"SWAYSOCK":"/run/s","DISPLAY":":0"},yes),("sway",""))
        self.assertEqual(disp.backend({"DISPLAY":":0"},yes),("xrandr",""))
        self.assertEqual(disp.backend({"WAYLAND_DISPLAY":"wayland-0"},yes)[0],"")
        self.assertIn("xrandr was not found",disp.backend({"DISPLAY":":0"},lambda _n:False)[1])

class ArrangeTests(unittest.TestCase):
    def test_reads_the_arrangement(self):
        outs=outputs()
        self.assertEqual(disp.placements(outs),{"DP-1":("right","HDMI-1")})
    def test_a_smaller_resolution_keeps_the_neighbour_against_it(self):
        new=disp.edited(outputs(),"HDMI-1",mode=(1280,720,False))
        hdmi,dp=by(new,"HDMI-1"),by(new,"DP-1")
        self.assertEqual((hdmi.width,hdmi.rate),(1280,60.0)); self.assertEqual((dp.x,dp.y),(1280,0))
    def test_keeps_the_rate_when_the_new_mode_has_it_else_takes_the_highest(self):
        self.assertEqual(by(disp.edited(outputs(),"DP-1",mode=(1920,1080,False)),"DP-1").rate,60.0)
        self.assertEqual(by(disp.edited(outputs(),"HDMI-1",mode=(1280,720,False),rate=59.94),"HDMI-1").rate,59.94)
    def test_moving_a_display(self):
        new=disp.edited(outputs(),"DP-1",place=("left","HDMI-1"))
        self.assertEqual((by(new,"DP-1").x,by(new,"DP-1").y),(0,0)); self.assertEqual((by(new,"HDMI-1").x,by(new,"HDMI-1").y),(2560,0))
        new=disp.edited(outputs(),"DP-1",place=("below","HDMI-1"))
        self.assertEqual((by(new,"HDMI-1").x,by(new,"HDMI-1").y,by(new,"DP-1").x,by(new,"DP-1").y),(0,0,0,1080))
        new=disp.edited(outputs(),"DP-1",place=("mirror","HDMI-1"))
        self.assertEqual((by(new,"DP-1").x,by(new,"DP-1").y),(0,0))
    def test_moving_the_primary_display_moves_the_other_instead(self):
        new=disp.edited(outputs(),"HDMI-1",place=("right","DP-1"))
        self.assertEqual((by(new,"DP-1").x,by(new,"HDMI-1").x),(0,2560))
    def test_switching_a_display_on_puts_it_at_the_right_end(self):
        new=disp.edited(outputs(),"VGA-1",enabled=True)
        vga=by(new,"VGA-1"); self.assertTrue(vga.enabled); self.assertEqual((vga.width,vga.x,vga.y),(1024,1920+2560,0))
    def test_a_row_of_three_closes_up_when_the_middle_one_goes_off(self):
        on=disp.edited(outputs(),"VGA-1",enabled=True)
        off=disp.edited(on,"DP-1",enabled=False)
        self.assertEqual(by(off,"VGA-1").x,1920); self.assertFalse(by(off,"DP-1").enabled)
    def test_switching_the_primary_off_hands_primary_on(self):
        new=disp.edited(outputs(),"HDMI-1",enabled=False)
        self.assertTrue(by(new,"DP-1").primary); self.assertEqual(by(new,"DP-1").x,0)
    def test_primary_changes_only_the_flag(self):
        new=disp.edited(outputs(),"DP-1",primary=True)
        self.assertEqual([(o.name,o.primary,o.x,o.y) for o in new if o.enabled],[("HDMI-1",False,0,180),("DP-1",True,1920,0)])
    def test_anchors_to_the_display_it_shares_the_longest_edge_with(self):
        outs=disp.edited(disp.edited(outputs(),"VGA-1",enabled=True),"VGA-1",place=("below","DP-1"))
        outs=disp.edited(outs,"DP-1",primary=True)
        self.assertEqual(disp.placements(outs)["HDMI-1"],("left","DP-1"))
    def test_a_display_placed_where_another_is_goes_past_it(self):
        on=disp.edited(outputs(),"VGA-1",enabled=True)
        new=disp.edited(on,"VGA-1",place=("right","HDMI-1"))   # DP-1 is already there
        self.assertEqual(by(new,"VGA-1").x,1920+2560)
    def test_choices_name_every_other_display_that_is_on(self):
        outs=outputs(); keys=[k for k,_t in disp.choices(outs,by(outs,"DP-1"))]
        self.assertEqual(keys,["right:HDMI-1","left:HDMI-1","below:HDMI-1","above:HDMI-1","mirror:HDMI-1"])

class CommandTests(unittest.TestCase):
    def test_xrandr_argv(self):
        new=disp.edited(outputs(),"HDMI-1",mode=(1280,720,False))
        self.assertEqual(disp.xrandr_argv(new),["xrandr","--output","HDMI-1","--mode","1280x720","--rate","60.00","--scale","1x1","--pos","0x0","--primary",
                         "--output","DP-1","--mode","2560x1440","--rate","143.97","--scale","1x1","--pos","1280x0","--output","VGA-1","--off"])
    def test_interlaced_mode_is_named_as_xrandr_names_it(self):
        new=disp.edited(outputs(),"HDMI-1",mode=(1920,1080,True))
        argv=disp.xrandr_argv(new); self.assertEqual(argv[argv.index("HDMI-1")+2],"1920x1080i")
    def test_sway_command(self):
        tv,laptop=disp.parse_sway(SWAY)
        self.assertEqual(disp.sway_command([tv,laptop]),'output "HDMI-A-1" enable mode 3840x2160@60.000Hz scale 2 position 0 0; output "eDP-1" disable')
    def test_never_switches_every_display_off(self):
        outs=outputs()
        for o in outs: o.enabled=False
        self.assertIn("At least one",disp.apply(disp.DisplayState(True,"xrandr","",outs),outs))

SCALED="""Screen 0: minimum 320 x 200, current 5120 x 2880, maximum 16384 x 16384
HDMI-1 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 527mm x 296mm
   1920x1080     60.00*+  50.00
   1280x720      60.00
"""

class ScaleTests(unittest.TestCase):
    def test_xrandr_scaled_display_reads_its_mode_and_scale(self):
        o,=disp.with_ui(outputs(SCALED),2.0)   # drawn at 200 %, shrunk by 4/3: 150 %
        self.assertEqual((o.width,o.height,o.scale,o.ui,o.size,round(o.zoom,6)),(1920,1080,1.5,2.0,(2560,1440),1.333333))
        o,=disp.with_ui(outputs(SCALED),1.0)
        self.assertEqual(o.scale,0.75)
    def test_session_scale_on_x11(self):
        new=disp.scaled(outputs(),1.5)
        hdmi,dp=by(new,"HDMI-1"),by(new,"DP-1")
        self.assertEqual((hdmi.ui,hdmi.scale,hdmi.size),(2.0,1.5,(2560,1440)))
        self.assertEqual((dp.x,dp.y),(2560,0))   # still against it
        argv=disp.xrandr_argv(new); self.assertEqual(argv[argv.index("HDMI-1")+5:argv.index("HDMI-1")+7],["--scale","1.333333333x1.333333333"])
        whole=disp.scaled(outputs(),2)
        self.assertEqual([(o.ui,o.zoom) for o in whole],[(2.0,1.0)]*3); self.assertEqual(by(whole,"DP-1").x,1920)   # a whole step: the desktop keeps its size
    def test_a_display_switched_on_takes_the_session_scale(self):
        vga=by(disp.edited(disp.scaled(outputs(),2),"VGA-1",enabled=True),"VGA-1")
        self.assertEqual((vga.ui,vga.scale),(2.0,2.0))
    def test_sway_scale_per_display(self):
        tv,laptop=disp.parse_sway(SWAY)
        new=disp.edited([tv,laptop],"HDMI-A-1",scale=1.5)
        self.assertEqual(by(new,"HDMI-A-1").size,(2560,1440)); self.assertIn("scale 1.5 ",disp.sway_command(new))
    def test_choices(self):
        outs=outputs()   # the smallest display that is on is 1080 high
        self.assertEqual(disp.scale_choices(outs,False),[1.0,2.0])
        self.assertEqual(disp.scale_choices(outs,True),[1.0,1.25,1.5,1.75,2.0])
        self.assertEqual(disp.scale_choices(outs,False,1.5),[1.0,1.5,2.0])
        self.assertEqual(disp.scale_text(1.25),"125 %"); self.assertEqual(disp.parse_xft_dpi("Xft.dpi:\t192\nXft.hinting:\t1"),192.0)
    def test_fractional_choice_is_kept_beside_the_displays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"displays.json"
            self.assertFalse(disp.fractional_on(outputs(),path))
            disp.set_fractional(True,path); self.assertTrue(disp.fractional_on(outputs(),path))
            state=disp.DisplayState(True,"xrandr","",outputs())
            disp.save(state,state.outputs,path); self.assertTrue(json.loads(path.read_text())["xrandr"]["fractional"])
            disp.set_fractional(False,path); self.assertFalse(disp.fractional_on(outputs(),path))
            self.assertTrue(disp.fractional_on(disp.scaled(outputs(),1.5),path))   # one in use: offered anyway
    def test_scale_is_saved_and_restored_for_its_own_backend_only(self):
        x=disp.DisplayState(True,"xrandr","",outputs())
        saved=disp.to_saved(x,disp.scaled(x.outputs,1.5))
        back=disp.from_saved(x,saved); self.assertEqual((by(back,"HDMI-1").scale,by(back,"HDMI-1").ui),(1.5,2.0))
        tv,laptop=disp.parse_sway(SWAY)
        sway=disp.DisplayState(True,"sway","",[tv])
        self.assertIsNotNone(disp.from_saved(sway,{"xrandr":{"outputs":{"HDMI-1":saved["xrandr"]["outputs"]["HDMI-1"]}}}))
        self.assertEqual(disp.from_saved(sway,{"xrandr":{"outputs":{"HDMI-1":dict(saved["xrandr"]["outputs"]["HDMI-1"],width=3840,height=2160)}}})[0].scale,2.0)
    def test_xsettings_and_xresources(self):
        self.assertEqual(disp.xsettings_text(2),"Gdk/WindowScalingFactor 2\nGdk/UnscaledDPI 98304\nXft/DPI 196608\n")
        self.assertEqual(disp.xresources_text(2),"Xft.dpi: 192\nXcursor.size: 48\n")
        mine="Xft.antialias: 1\n"
        with_scale=disp.with_xresources(mine,2)
        self.assertTrue(with_scale.startswith(mine)); self.assertIn("Xft.dpi: 192",with_scale)
        self.assertEqual(disp.with_xresources(disp.with_xresources(with_scale,3),1),mine)   # replaced, then taken out
        self.assertEqual(disp.with_xresources("",1),"")

class SavedTests(unittest.TestCase):
    def test_saved_settings_come_back_only_for_the_same_displays(self):
        state=disp.DisplayState(True,"xrandr","",outputs())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"tvwcs"/"displays.json"
            disp.save(state,disp.edited(state.outputs,"HDMI-1",mode=(1280,720,False)),path)
            saved=json.loads(path.read_text())
        back=disp.from_saved(state,saved)
        self.assertEqual((by(back,"HDMI-1").width,by(back,"DP-1").x),(1280,1280))
        fewer=disp.DisplayState(True,"xrandr","",[o for o in outputs() if o.name!="VGA-1"])
        self.assertIsNone(disp.from_saved(fewer,saved))
        self.assertIsNotNone(disp.from_saved(disp.DisplayState(True,"sway","",outputs()),saved))   # no sway entry yet: X's is used
    def test_each_backend_keeps_its_own_settings(self):
        x=disp.DisplayState(True,"xrandr","",outputs())
        sway_outs=outputs()
        for o in sway_outs:
            if o.name=="HDMI-1": o.name="HDMI-A-1"
        sway=disp.DisplayState(True,"sway","",sway_outs)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"displays.json"
            disp.save(x,disp.edited(x.outputs,"HDMI-1",mode=(1280,720,False)),path)
            first=disp.from_saved(sway,json.loads(path.read_text()))                 # sway's first start: X's mode, by connector
            self.assertEqual(by(first,"HDMI-A-1").width,1280)
            disp.save(sway,sway.outputs,path)                                          # kept under sway at its own mode
            saved=json.loads(path.read_text()); self.assertEqual(set(saved),{"xrandr","sway"})
            self.assertEqual(by(disp.from_saved(x,saved),"HDMI-1").width,1280)       # i3's is untouched
            self.assertEqual(by(disp.from_saved(sway,saved),"HDMI-A-1").width,by(sway.outputs,"HDMI-A-1").width)
    def test_a_file_from_before_3_0_1_still_loads(self):
        x=disp.DisplayState(True,"xrandr","",outputs())
        old={"backend":"xrandr","outputs":disp.to_saved(x,disp.edited(x.outputs,"HDMI-1",mode=(1280,720,False)))["xrandr"]["outputs"]}
        self.assertEqual(by(disp.from_saved(x,old),"HDMI-1").width,1280)

if __name__=="__main__": unittest.main()
