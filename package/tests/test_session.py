import os, tempfile, time, unittest
from pathlib import Path
from tvwcs.session import first_time_this_login, is_tvwcs_process, runtime_dir, session_key

class SessionTests(unittest.TestCase):
    def test_runtime_dir_falls_back_to_the_users_cache(self):
        self.assertEqual(runtime_dir({"XDG_RUNTIME_DIR":"/run/user/7"}),Path("/run/user/7"))
        self.assertEqual(runtime_dir({"HOME":"/home/a"}),Path("/home/a/.cache/tvwcs"))
        self.assertEqual(runtime_dir({"HOME":"/home/a","XDG_CACHE_HOME":"/c"}),Path("/c/tvwcs"))
    def test_once_per_login_without_a_runtime_dir_that_empties(self):
        with tempfile.TemporaryDirectory() as d:
            boot=Path(d)/"boot_id"; boot.write_text("boot-1\n"); sock=Path(d)/"ipc-socket.100"; sock.write_text("")
            marker=Path(d)/"cache"/"tvwcs-startup-done"; env={"I3SOCK":str(sock)}
            self.assertTrue(first_time_this_login(marker,env,boot)); self.assertFalse(first_time_this_login(marker,env,boot))   # TVWCS restarted
            sock.unlink(); time.sleep(0.01); sock.write_text("")   # the next login: i3 makes its socket again
            self.assertTrue(first_time_this_login(marker,env,boot)); self.assertFalse(first_time_this_login(marker,env,boot))
            boot.write_text("boot-2\n"); self.assertTrue(first_time_this_login(marker,env,boot))   # a reboot
            self.assertNotEqual(session_key({"SWAYSOCK":"/run/a.1.sock"},boot),session_key({"SWAYSOCK":"/run/a.2.sock"},boot))
    def test_a_stale_pid_naming_another_program_is_not_tvwcs(self):
        with tempfile.TemporaryDirectory() as d:
            proc=Path(d); (proc/str(os.getpid())).mkdir(); cmd=proc/str(os.getpid())/"cmdline"
            cmd.write_bytes(b"python3\0-m\0tvwcs.main\0"); self.assertTrue(is_tvwcs_process(os.getpid(),proc))
            cmd.write_bytes(b"/usr/bin/firefox\0"); self.assertFalse(is_tvwcs_process(os.getpid(),proc))
            self.assertFalse(is_tvwcs_process(2**22+12345,proc)); self.assertFalse(is_tvwcs_process("x",proc))
if __name__=="__main__": unittest.main()
