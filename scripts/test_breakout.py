"""Headless unit tests for Breakout arcade mini-game logic."""
import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_dir = os.path.join(repo_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Set SDL to dummy for headless execution
os.environ["SDL_VIDEODRIVER"] = "dummy"

from games.breakout import BreakoutGame, Particle, Brick


class TestBreakoutGame(unittest.TestCase):
    def setUp(self):
        self.game = BreakoutGame(width=800, height=600)

    def test_initial_state(self):
        self.assertEqual(self.game.state, BreakoutGame.STATE_READY)
        self.assertEqual(self.game.lives, 3)
        self.assertEqual(self.game.score, 0)
        self.assertEqual(len(self.game.bricks), 50)  # 5 rows x 10 cols
        self.assertTrue(all(b.alive for b in self.game.bricks))

    def test_paddle_bounds(self):
        # Move hard left
        for _ in range(20):
            self.game.update(dt=0.1, axis_x=-1.0)
        self.assertGreaterEqual(self.game.paddle_x, 8.0)

        # Move hard right
        for _ in range(40):
            self.game.update(dt=0.1, axis_x=1.0)
        max_x = self.game.width - self.game.paddle_w - 8.0
        self.assertLessEqual(self.game.paddle_x, max_x)

    def test_launch_ball(self):
        self.assertEqual(self.game.state, BreakoutGame.STATE_READY)
        # Action trigger launches
        self.game.update(dt=0.016, action=True)
        self.assertEqual(self.game.state, BreakoutGame.STATE_PLAYING)
        self.assertLess(self.game.ball_vy, 0)  # moving upward

    def test_brick_collision_and_scoring(self):
        self.game.launch_ball()
        # Position ball right below a brick
        target_brick = self.game.bricks[0]
        self.game.ball_x = target_brick.rect.centerx
        self.game.ball_y = target_brick.rect.bottom + 5
        self.game.ball_vy = -200
        self.game.ball_vx = 0

        # Run a tick that hits the brick
        initial_score = self.game.score
        self.game.update(dt=0.04)

        self.assertFalse(target_brick.alive)
        self.assertGreater(self.game.score, initial_score)
        self.assertGreater(self.game.ball_vy, 0)  # deflected downward
        self.assertGreater(len(self.game.particles), 0)  # particles spawned

    def test_ball_loss_and_game_over(self):
        self.game.launch_ball()
        self.game.ball_vy = 300
        self.game.ball_y = self.game.height + 10  # ball fell past bottom
        self.game.update(dt=0.016)

        self.assertEqual(self.game.lives, 2)
        self.assertEqual(self.game.state, BreakoutGame.STATE_BALL_LOST)


if __name__ == "__main__":
    unittest.main()
