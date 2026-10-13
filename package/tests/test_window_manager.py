import unittest
from tvwcs.window_manager import I3WindowManager
from tvwcs.model import LAUNCH_NEW_WORKSPACE, LAUNCH_SAME

def con(i,title,cls,urgent=False):
    return {"type":"con","id":i,"window":100+i,"name":title,"urgent":urgent,"window_properties":{"title":title,"class":cls,"instance":cls},"nodes":[],"floating_nodes":[]}

TREE={"type":"root","nodes":[
  {"type":"output","name":"HDMI-1","nodes":[
    {"type":"workspace","name":"1: main","visible":True,"nodes":[con(10,"Firefox — Video","firefox"),con(11,"i3bar for output HDMI-1","i3bar"),con(12,"(4) Inbox","thunderbird",True)],"floating_nodes":[]},
    {"type":"workspace","name":"2","visible":False,"nodes":[con(13,"Terminal","xterm")],"floating_nodes":[]},
    {"type":"workspace","name":"3","visible":False,"nodes":[con(14,"A","a"),con(15,"B","b")],"floating_nodes":[con(16,"TVWCS","tvwcs"),con(17,"TVWCS · Launch Profile","tvwcs")]},
  ],"floating_nodes":[]},
  {"type":"output","name":"__i3","nodes":[{"type":"workspace","name":"__i3_scratch","nodes":[],"floating_nodes":[con(18,"Hidden 1","h"),con(19,"Hidden 2","h")]}],"floating_nodes":[]},
],"floating_nodes":[]}

class FakeWM(I3WindowManager):
    """i3 adapter whose IPC is replaced by a recorder."""
    def __init__(self,workspaces=(),outputs=()):
        super().__init__(); self.binary="/bin/i3-msg"; self.xdotool=None; self.sent=[]; self._ws=list(workspaces); self._out=list(outputs)
    def _tree(self): return TREE
    def workspaces(self): return self._ws
    def outputs(self): return self._out
    def _call(self,*args,timeout=2):
        self.sent.append(" ".join(args)); return '[{"success":true}]'

class WindowManagerTests(unittest.TestCase):
    def test_windows_exclude_bars_and_tvwcs(self):
        wm=FakeWM(); titles={w["title"] for w in wm.windows()}
        self.assertIn("Firefox — Video",titles); self.assertNotIn("i3bar for output HDMI-1",titles)
        self.assertFalse({"TVWCS","TVWCS · Launch Profile"}&titles)
    def test_document_named_like_tvwcs_is_not_hidden(self):
        tree=TREE["nodes"][0]["nodes"][1]["nodes"]
        tree.append(con(30,"tvwcs.conf - Text Editor","gedit")); tree.append(con(31,"TVWCS_notes.txt - Mousepad","mousepad"))
        try: titles={w["title"] for w in FakeWM().windows()}
        finally: del tree[-2:]
        self.assertIn("tvwcs.conf - Text Editor",titles); self.assertIn("TVWCS_notes.txt - Mousepad",titles)
    def test_untitled_window_is_listed_by_class(self):
        tree=TREE["nodes"][0]["nodes"][1]["nodes"]; tree.append(con(32,"","gedit"))
        try: found=[w for w in FakeWM().windows() if w["con_id"]==32]
        finally: del tree[-1]
        self.assertEqual(found[0]["title"],"gedit")
    def test_windows_know_whether_their_workspace_is_on_screen(self):
        wm=FakeWM(workspaces=[{"name":"1: main","visible":True},{"name":"2","visible":False},{"name":"3","visible":False}])
        by_id={x["con_id"]:x for x in wm.windows()}
        self.assertTrue(by_id[10]["workspace_visible"]); self.assertFalse(by_id[13]["workspace_visible"]); self.assertFalse(by_id[18]["workspace_visible"])   # 18: parked
    def test_find_matching_returns_the_window_without_focusing_it(self):
        from tvwcs.model import LaunchProfile
        wm=FakeWM(); found=wm.find_matching(LaunchProfile("p","xterm.desktop","Terminal"),None)
        self.assertEqual(found["con_id"],13); self.assertEqual(wm.sent,[])
        self.assertIsNone(wm.find_matching(LaunchProfile("p","nothing.desktop","Nope"),None))
    def test_window_fields(self):
        w=next(w for w in FakeWM().windows() if w["con_id"]==12)
        self.assertEqual((w["workspace"],w["output"],w["urgent"]),("1: main","HDMI-1",True))
    def test_new_workspace_number_is_lowest_free(self):
        wm=FakeWM(workspaces=[{"name":"1: main","num":1},{"name":"2","num":2},{"name":"4","num":4},{"name":"misc","num":-1}])
        self.assertEqual(wm.new_workspace_number(),3)
    def test_prepare_for_launch_modes(self):
        wm=FakeWM(workspaces=[{"name":"1","num":1,"focused":True}])
        self.assertIsNone(wm.prepare_for_launch(LAUNCH_SAME)); self.assertFalse(any(c.startswith("workspace number") for c in wm.sent))
        self.assertEqual(wm.prepare_for_launch(LAUNCH_NEW_WORKSPACE),"2"); self.assertIn("workspace number 2",wm.sent)
    def test_focus_same_pulls_window_to_current_workspace(self):
        wm=FakeWM(); self.assertTrue(wm.focus(13,LAUNCH_SAME))
        self.assertIn("[con_id=13] move container to workspace current",wm.sent)
    def test_focus_new_workspace_mode_just_shows_a_lone_window(self):
        wm=FakeWM(); self.assertTrue(wm.focus(13,LAUNCH_NEW_WORKSPACE))   # alone on workspace "2"
        self.assertFalse(any("move container" in c for c in wm.sent)); self.assertIn("[con_id=13] focus",wm.sent)
    def test_focus_new_workspace_mode_splits_a_shared_window_off(self):
        wm=FakeWM(workspaces=[{"name":"1: main","num":1},{"name":"2","num":2},{"name":"3","num":3}]); self.assertTrue(wm.focus(14,LAUNCH_NEW_WORKSPACE))   # shares "3"
        self.assertIn("[con_id=14] move container to workspace number 4",wm.sent)
    def test_close_workspace_kills_each_window(self):
        wm=FakeWM(); self.assertTrue(wm.close_workspace("3"))
        self.assertEqual(sorted(c for c in wm.sent if c.endswith("kill")),["[con_id=14] kill","[con_id=15] kill"])
        self.assertFalse(FakeWM().close_workspace("nope"))
    def test_focus_parked_window_gets_its_own_workspace(self):
        wm=FakeWM(workspaces=[{"name":"1","num":1}]); wm.focus(18,LAUNCH_NEW_WORKSPACE)
        self.assertIn("[con_id=18] move container to workspace number 2",wm.sent)
    def test_place_tvwcs_command(self):
        wm=FakeWM(); wm.place_tvwcs(20,50,460,1010)
        self.assertEqual(wm.sent[-1],'[title="^TVWCS$"] floating enable, border pixel 0, resize set 460 1010, move absolute position 20 50')
    def test_focus_workspace_brings_it_to_pointer_output(self):
        wm=FakeWM(workspaces=[{"name":"3","output":"HDMI-2","num":3},{"name":"1","output":"HDMI-1","num":1,"focused":True}],outputs=[{"name":"HDMI-1"},{"name":"HDMI-2"}])
        wm.focus_output_under_mouse=lambda: "HDMI-1"
        wm.focus_workspace("3"); self.assertEqual(wm.sent,['workspace "3"',"move workspace to output HDMI-1"])
    def test_move_workspace_to_chosen_output(self):
        wm=FakeWM(outputs=[{"name":"HDMI-1"},{"name":"HDMI-2"}])
        self.assertTrue(wm.move_workspace_to_output("3","HDMI-2")); self.assertEqual(wm.sent,['workspace "3"',"move workspace to output HDMI-2"])
        self.assertFalse(wm.move_workspace_to_output("3","DP-9"))
    def test_workspace_name_is_quoted(self):
        wm=FakeWM(workspaces=[{"name":'we"ird',"output":"A","num":-1,"focused":True}],outputs=[{"name":"A"}]); wm.focus_output_under_mouse=lambda:"A"
        wm.focus_workspace('we"ird'); self.assertEqual(wm.sent[0],'workspace "we\\"ird"')
if __name__=="__main__": unittest.main()
