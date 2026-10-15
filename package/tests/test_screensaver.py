import random, unittest
from tvwcs import screensaver as S

class ScreensaverTests(unittest.TestCase):
    def test_moves_without_bouncing_in_the_middle(self):
        self.assertEqual(S.step(100,100,2,2,50,20,1920,1080),(102,102,2,2,False))
    def test_bounces_off_the_right_and_bottom_edges(self):
        x,y,dx,dy,b=S.step(1869,1059,2,2,50,20,1920,1080)
        self.assertTrue(b); self.assertEqual((x,y),(1870,1060)); self.assertEqual((dx,dy),(-2,-2))
    def test_bounces_off_the_left_and_top_edges(self):
        x,y,dx,dy,b=S.step(1,1,-2,-2,50,20,1920,1080)
        self.assertTrue(b); self.assertEqual((x,y,dx,dy),(0,0,2,2))
    def test_stays_on_screen_for_a_long_time(self):
        x,y,dx,dy=10.0,10.0,2.2,2.2
        for _ in range(20000):
            x,y,dx,dy,_b=S.step(x,y,dx,dy,384,192,1920,1080)
            self.assertTrue(0<=x<=1920-384 and 0<=y<=1080-192)
    def test_next_colour_changes(self):
        rng=random.Random(1)
        for c in S.COLOURS: self.assertNotEqual(S.next_colour(c,rng),c)
    def test_logo_size(self):
        self.assertEqual(S.logo_size(1920,1080),(384,192))
        w,h=S.logo_size(1920,400,2.0); self.assertLessEqual(h,100); self.assertEqual(w,h*2)

if __name__=="__main__": unittest.main()
