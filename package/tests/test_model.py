import json, tempfile, unittest
from pathlib import Path
from tvwcs.model import (ConfigStore, LaunchProfile, LAUNCH_SAME, LAUNCH_NEW_WORKSPACE, compute_layout, extract_badge, is_tvwcs_title, profile_detail, row_description, search_items, startup_choices, PIN_LAUNCH, PIN_LAUNCH_AND_SHOW)
from tvwcs.applications import Application

class ModelTests(unittest.TestCase):
    def test_channel_uniqueness_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            store=ConfigStore(Path(d)/"config.json")
            store.set_profile(LaunchProfile("1","firefox.desktop","Firefox",channel=42))
            with self.assertRaises(ValueError): store.set_profile(LaunchProfile("2","chromium.desktop","Chromium",channel=42))
            self.assertEqual(ConfigStore(Path(d)/"config.json").assigned()[0].channel,42)
    def test_launch_mode_defaults_to_same_workspace(self):
        self.assertEqual(LaunchProfile("1","a.desktop","A").launch_mode,LAUNCH_SAME)
    def test_launch_mode_persists_and_toggles(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"config.json"; store=ConfigStore(path)
            store.set_profile(LaunchProfile("p","firefox.desktop","Firefox",launch_mode=LAUNCH_NEW_WORKSPACE))
            self.assertEqual(ConfigStore(path).get("p").launch_mode,LAUNCH_NEW_WORKSPACE)
            self.assertEqual(store.toggle_launch_mode("p"),LAUNCH_SAME)
            self.assertEqual(ConfigStore(path).get("p").launch_mode,LAUNCH_SAME)
            self.assertEqual(store.toggle_launch_mode("p"),LAUNCH_NEW_WORKSPACE)
            self.assertIsNone(store.toggle_launch_mode("missing"))
    def test_invalid_launch_mode_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): ConfigStore(Path(d)/"c.json").set_profile(LaunchProfile("p","a.desktop","A",launch_mode="bogus"))
    def test_legacy_config_loads(self):
        # 2.2 files have "tile" and no launch_mode or settings block.
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"config.json"
            path.write_text(json.dumps({"version":1,"profiles":[{"id":"x","desktop_id":"a.desktop","name":"A","tile":False,"favorite":True,"channel":7}]}))
            store=ConfigStore(path); p=store.get("x")
            self.assertEqual((p.launch_mode,p.favorite,p.channel),(LAUNCH_SAME,True,7))
            self.assertEqual(store.settings["margin"],20)
    def test_settings_validated(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"config.json"
            path.write_text(json.dumps({"settings":{"margin":9999,"quick_width":500,"accent":"red","lock_command":" i3lock "},"profiles":[]}))
            s=ConfigStore(path).settings
            self.assertEqual((s["margin"],s["quick_width"],s["accent"],s["lock_command"]),(20,500,"#0078d7","i3lock"))
    def test_desktop_action_persists(self):
        with tempfile.TemporaryDirectory() as d:
            store=ConfigStore(Path(d)/"config.json")
            store.set_profile(LaunchProfile("a","browser.desktop","Private Window",desktop_action="Private"))
            self.assertEqual(ConfigStore(Path(d)/"config.json").get("a").desktop_action,"Private")
    def test_numeric_search(self):
        p=LaunchProfile("1","firefox.desktop","Stream",channel=12)
        app=Application("firefox.desktop","Firefox",None,None,None,("Internet",),"/fake","firefox")
        self.assertEqual([r["id"] for r in search_items("12",[p],{app.desktop_id:app},[])],["1"])
    def test_favorite_independent_of_channel(self):
        with tempfile.TemporaryDirectory() as d:
            store=ConfigStore(Path(d)/"config.json"); store.set_profile(LaunchProfile("1","firefox.desktop","Stream",favorite=True))
            self.assertIsNone(store.favorites()[0].channel); self.assertEqual(store.assigned(),[])

class SettingsAndProfileTests(unittest.TestCase):
    def test_new_settings_defaults_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"
            s=ConfigStore(path).settings
            self.assertEqual((s["scale"],s["close_on_click_outside"],s["open_in_new_workspace"],s["hotkeys"],s["startup"]["mode"]),("desktop",False,False,{"keyboard":{"menu":"Mod4","guide":""},"remote":{"menu":"F2","guide":"Shift+F2"},"gamepad":{"menu":"","guide":""}},"none"))
            path.write_text(json.dumps({"settings":{"scale":"huge","close_on_click_outside":True,"open_in_new_workspace":"yes","hotkeys":{"keyboard":{"menu":"Mod1","guide":"bad key"},"gamepad":{"menu":"F7"}},"startup":{"mode":"app","profile_id":"p1"}}}))
            s=ConfigStore(path).settings
            self.assertEqual((s["scale"],s["close_on_click_outside"],s["open_in_new_workspace"]),("desktop",True,False))
            self.assertEqual(s["hotkeys"],{"keyboard":{"menu":"Mod1","guide":""},"remote":{"menu":"F2","guide":"Shift+F2"},"gamepad":{"menu":"F7","guide":""}}); self.assertEqual((s["startup"]["mode"],s["startup"]["profile_id"]),("app","p1"))
    def test_a_key_used_twice_keeps_only_its_first_use(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; path.write_text(json.dumps({"settings":{"hotkeys":{"remote":{"menu":"F5","guide":"F5"},"gamepad":{"menu":"Mod4"}}}}))
            hk=ConfigStore(path).settings["hotkeys"]
            self.assertEqual((hk["remote"],hk["gamepad"]["menu"]),({"menu":"F5","guide":""},""))   # Mod4 is already the keyboard's
    def test_old_single_hotkey_set_becomes_the_remote_set(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; path.write_text(json.dumps({"settings":{"hotkeys":{"menu":"F9","guide":"Shift+F9"}}}))
            hk=ConfigStore(path).settings["hotkeys"]
            self.assertEqual((hk["remote"],hk["keyboard"]["menu"]),({"menu":"F9","guide":"Shift+F9"},"Mod4"))
    def test_defaults_are_not_shared_between_stores(self):
        with tempfile.TemporaryDirectory() as d:
            a=ConfigStore(Path(d)/"a.json"); a.settings["hotkeys"]["remote"]["menu"]="F9"
            self.assertEqual(ConfigStore(Path(d)/"b.json").settings["hotkeys"]["remote"]["menu"],"F2")
    def test_pin_fields_persist_and_are_validated(self):
        from tvwcs.pinlock import make_hash
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; store=ConfigStore(path); h=make_hash("1234")
            store.set_profile(LaunchProfile("p","a.desktop","A",pin_hash=h,pin_scope=PIN_LAUNCH_AND_SHOW))
            p=ConfigStore(path).get("p"); self.assertEqual((p.pin_hash,p.pin_scope),(h,PIN_LAUNCH_AND_SHOW))
            with self.assertRaises(ValueError): store.set_profile(LaunchProfile("q","a.desktop","A",pin_scope="nope"))
            with self.assertRaises(ValueError): store.set_profile(LaunchProfile("q","a.desktop","A",pin_hash="1234"))   # a plaintext PIN is refused
    def test_hand_edited_bad_pin_data_is_dropped_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; path.write_text(json.dumps({"profiles":[{"id":"x","desktop_id":"a.desktop","name":"A","pin_hash":"1234","pin_scope":"weird"}]}))
            p=ConfigStore(path).get("x"); self.assertEqual((p.pin_hash,p.pin_scope),("",PIN_LAUNCH))
    def test_old_run_as_user_key_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; path.write_text(json.dumps({"profiles":[{"id":"x","desktop_id":"a.desktop","name":"A","run_as_user":"bob"}]}))
            store=ConfigStore(path); self.assertEqual(store.get("x").name,"A"); self.assertFalse(hasattr(store.get("x"),"run_as_user"))
    def test_profile_description_override_persists(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; store=ConfigStore(path)
            store.set_profile(LaunchProfile("p","a.desktop","A",description="  Kids   profile "))
            self.assertEqual(ConfigStore(path).get("p").description,"Kids profile")
    def test_app_description_override_persists_and_clears(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; store=ConfigStore(path)
            store.set_app_description("a.desktop","My own words"); self.assertEqual(ConfigStore(path).app_descriptions,{"a.desktop":"My own words"})
            store.set_app_description("a.desktop","   "); self.assertEqual(ConfigStore(path).app_descriptions,{})
    def test_row_description_defaults_and_overrides(self):
        app=Application("b.desktop","B","Generic","The .desktop comment",None,("Internet",),"/x","b",(("Private","Private Window"),))
        main=LaunchProfile("1","b.desktop","B"); sec=LaunchProfile("2","b.desktop","P",command="b --kiosk",desktop_action="Private")
        self.assertEqual(row_description(main,app,True),"The .desktop comment")                      # main: the .desktop description
        self.assertEqual(row_description(main,app,True,"Override"),"Override")                        # ... unless overridden
        self.assertEqual(row_description(sec,app,False),"Private Window  ·  b --kiosk")             # secondary: its launch options
        sec.description="Just for me"; self.assertEqual(row_description(sec,app,False),"Just for me")
    def test_startup_choices_order(self):
        ps=[LaunchProfile("a","a.desktop","Zed"),LaunchProfile("b","b.desktop","Alpha",channel=9),LaunchProfile("c","c.desktop","Mid",favorite=True,channel=5),
            LaunchProfile("d","d.desktop","Beta",favorite=True),LaunchProfile("e","e.desktop","Chan",channel=2)]
        got=[(t,[p.name for p in g]) for t,g in startup_choices(ps)]
        self.assertEqual(got,[("FAVORITES",["Mid","Beta"]),("CHANNELS",["Chan","Alpha"]),("ALL OTHER APPS",["Zed"])])   # a favorite with a channel is listed once
        self.assertEqual([t for t,_ in startup_choices([LaunchProfile("a","a.desktop","Only")])],["ALL OTHER APPS"])
    def test_last_profile_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"c.json"; store=ConfigStore(path); store.record_last_profile("x")
            self.assertEqual(ConfigStore(path).settings["startup"]["last_profile_id"],"x")
    def test_tvwcs_title_is_exact_not_prefix(self):
        self.assertTrue(is_tvwcs_title("TVWCS")); self.assertTrue(is_tvwcs_title("TVWCS · Launch Profile"))
        for t in ("tvwcs.conf - Text Editor","TVWCS_notes.txt","TVWCS notes","TVWCS Launch Profile"): self.assertFalse(is_tvwcs_title(t),t)
    def test_profile_detail_lists_action_and_command(self):
        app=Application("b.desktop","B",None,"A browser",None,("Internet",),"/x","b",(("Private","Private Window"),))
        self.assertEqual(profile_detail(LaunchProfile("1","b.desktop","P",desktop_action="Private"),app),"Private Window")
        self.assertEqual(profile_detail(LaunchProfile("1","b.desktop","P",command="b --kiosk"),app),"b --kiosk")
        self.assertEqual(profile_detail(LaunchProfile("1","b.desktop","P",desktop_action="Private",command="b --x"),app),"Private Window  ·  b --x")
        self.assertEqual(profile_detail(LaunchProfile("1","b.desktop","P"),app),"")

class LayoutTests(unittest.TestCase):
    AREA={"x":0,"y":30,"width":1920,"height":1050}   # y offset = a 30 px bar on top
    def test_quick_menu_only(self):
        l=compute_layout(self.AREA,20,460,False)
        self.assertEqual((l.x,l.y,l.width,l.height),(20,50,460,1010))
        self.assertEqual(l.guide_width,0)
    def test_margin_is_equal_on_all_sides_with_guide(self):
        l=compute_layout(self.AREA,20,460,True)
        self.assertEqual(l.x-self.AREA["x"],20)                                            # left
        self.assertEqual(l.y-self.AREA["y"],20)                                            # top
        self.assertEqual(self.AREA["y"]+self.AREA["height"]-(l.y+l.height),20)             # bottom
        self.assertEqual(self.AREA["x"]+self.AREA["width"]-(l.x+l.width),20)               # right
        self.assertEqual(l.quick_width+l.margin+l.guide_width,l.width)                     # same gap between the two
    def test_three_panels(self):
        # Settings is a tab of the Applications window now: the extra argument is accepted and ignored.
        l=compute_layout(self.AREA,20,460,True,True)
        self.assertEqual(l.guide_width,l.width-l.quick_width-l.margin)                       # full middle, no third panel
        self.assertEqual(self.AREA["x"]+self.AREA["width"]-(l.x+l.width),20)                 # same margin at the right edge
        self.assertGreater(l.guide_width,l.quick_width)                                      # the guide still gets the middle
    def test_settings_panel_needs_the_guide(self):
        l=compute_layout(self.AREA,20,460,False,True)
        self.assertFalse(l.guide_open); self.assertEqual(l.width,460)
    def test_three_panels_on_a_small_screen(self):
        l=compute_layout({"x":0,"y":0,"width":1280,"height":720},20,460,True,True)
        self.assertGreaterEqual(l.guide_width,300)
    def test_second_monitor_offset(self):
        l=compute_layout({"x":1920,"y":0,"width":1920,"height":1080},20,460,False)
        self.assertEqual(l.x,1940)
    def test_small_screen_is_clamped(self):
        l=compute_layout({"x":0,"y":0,"width":800,"height":600},20,460,True)
        self.assertLessEqual(l.quick_width,int((800-40)*0.45)); self.assertGreater(l.guide_width,0)

class BadgeTests(unittest.TestCase):
    def test_count_in_title(self):
        self.assertEqual(extract_badge("(3) Inbox - Mail"),("Inbox - Mail","3"))
        self.assertEqual(extract_badge("[12] Chat"),("Chat","12"))
        self.assertEqual(extract_badge("(250) Feed")[1],"99+")
    def test_urgent_without_count(self):
        self.assertEqual(extract_badge("Terminal",True),("Terminal","!"))
        self.assertEqual(extract_badge("Terminal"),("Terminal",None))
    def test_not_a_badge(self):
        self.assertEqual(extract_badge("Report (draft 2)"),("Report (draft 2)",None))
    def test_window_search_result_carries_badge(self):
        r=search_items("inbox",[],{},[{"con_id":5,"title":"(2) Inbox","class":"mail","instance":"mail"}])[0]
        self.assertEqual((r["label"],r["badge"]),("Inbox","2"))

if __name__=="__main__": unittest.main()
