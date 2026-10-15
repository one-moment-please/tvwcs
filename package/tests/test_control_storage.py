import json, unittest
from tvwcs import control_storage as st

LSBLK={"blockdevices":[
  {"name":"loop0","path":"/dev/loop0","type":"loop","size":"100","fstype":"squashfs","mountpoints":["/snap/x"]},
  {"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","size":"256060514304","model":"Samsung SSD ","rm":False,"hotplug":False,"tran":"nvme","mountpoints":[None],
   "children":[{"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","size":"536870912","fstype":"vfat","mountpoints":["/boot/efi"]},
               {"name":"nvme0n1p2","path":"/dev/nvme0n1p2","type":"part","size":"255000000000","fstype":"ext4","label":"root","mountpoints":["/"],"fsused":"1000","fsavail":"2000"}]},
  {"name":"sdb","path":"/dev/sdb","type":"disk","size":"32000000000","model":"USB Stick","rm":True,"hotplug":True,"tran":"usb","mountpoints":[None],
   "children":[{"name":"sdb1","path":"/dev/sdb1","type":"part","size":"32000000000","fstype":"exfat","label":"MOVIES","mountpoints":[None]}]},
  {"name":"sr0","path":"/dev/sr0","type":"rom","size":"0"},
]}

class StorageTests(unittest.TestCase):
    def test_lsblk_drives_and_volumes(self):
        drives=st.parse_lsblk(json.dumps(LSBLK))
        self.assertEqual([d.name for d in drives],["nvme0n1","sdb"])   # the system drive first; loop and CD drives left out
        system,usb=drives
        self.assertTrue(system.system); self.assertEqual(system.title,"Samsung SSD")
        self.assertEqual([v.name for v in system.volumes],["nvme0n1p1","nvme0n1p2"]); self.assertEqual(system.volumes[1].used,1000)
        self.assertTrue(usb.removable); self.assertFalse(usb.system)
        self.assertEqual(usb.volumes[0].title,"MOVIES"); self.assertFalse(usb.volumes[0].mounted)
    def test_lsblk_drive_without_partitions(self):
        data={"blockdevices":[{"name":"sdc","path":"/dev/sdc","type":"disk","size":"1000","fstype":"vfat","label":"CAM","mountpoints":["/media/tv/CAM"],"rm":True}]}
        d=st.parse_lsblk(json.dumps(data))[0]
        self.assertEqual(len(d.volumes),1); self.assertTrue(d.volumes[0].mounted)
    def test_bad_lsblk_output(self):
        self.assertEqual(st.parse_lsblk("not json"),[])
    def test_size_text(self):
        self.assertEqual(st.size_text(1500000000),"1.5 GB"); self.assertEqual(st.size_text(256060514304),"256 GB"); self.assertEqual(st.size_text(512),"512 B")
    def test_valid_address(self):
        self.assertEqual(st.valid_address("smb://nas/videos"),"")
        self.assertIn("smb://",st.valid_address("nas/videos"))
        self.assertIn("computer's name",st.valid_address("smb:///videos"))
        self.assertIn("%20",st.valid_address("smb://nas/my videos"))
    def test_share_label_and_matching(self):
        self.assertEqual(st.share_label("smb://nas.local/Videos"),"Videos on nas.local")
        self.assertEqual(st.share_label("sftp://pi"),"pi")
        self.assertTrue(st.same_share("smb://NAS/videos/","smb://nas/videos"))
    def test_gio_mounts(self):
        text=("Drive(0): Samsung SSD\n  Type: GProxyDrive (GProxyVolumeMonitorUDisks2)\n"
              "Mount(0): videos on nas -> smb://nas/videos/\n  Type: GDaemonMount\n"
              "Mount(1): pi -> sftp://pi/\n")
        self.assertEqual(st.parse_gio_mounts(text),["smb://nas/videos","sftp://pi"])
    def test_gvfs_path(self):
        self.assertEqual(st.gvfs_path("smb://nas/Videos",uid=1000),"/run/user/1000/gvfs/smb-share:server=nas,share=videos")
        self.assertEqual(st.gvfs_path("sftp://tv@pi:2222/home",uid=1000),"/run/user/1000/gvfs/sftp:host=pi,port=2222,user=tv")
    def test_connect_answers(self):
        self.assertEqual(st.connect_answers("tv","pw"),"tv\n\npw\n")

if __name__=="__main__": unittest.main()
