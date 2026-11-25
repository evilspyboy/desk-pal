"""Unit tests for AttentionVoiceManager and progressive voice escalation ladder."""
import sys
import unittest
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path('src').resolve()))
from attention_voice import AttentionVoiceManager, DEFAULT_CONFIG
from activity_queue import ActivityQueue


class TestAttentionVoice(unittest.TestCase):
    def setUp(self):
        self.mgr = AttentionVoiceManager(config_dir='scratch')
        self.events = []
        self.spoken = []
        self.app = SimpleNamespace(
            radar_nearby_present=True,
            last_radar_nearby={'targets': [{'x': 0, 'y': 1.0, 'speed': 0}]},
            hardware_monitor=SimpleNamespace(
                lock=MagicMock(__enter__=lambda s: None, __exit__=lambda s, *a: None),
                config={'radar': {'enabled': True, 'presence_range_m': 2.0},
                        'speaker': {'enabled': True, 'output': 'default', 'volume': 0.8}}
            ),
            audit_activity=lambda event, **kw: self.events.append((event, kw)),
            activity_queue=ActivityQueue(),
            char_x=0, char_y=0, target_x=0, target_y=0,
            wander_timer=0,
            target_animation='idle', current_anim='idle',
            active_popup_modal=None, pending_popup_modal=None,
            action_sequence=lambda role: {'frames': ['f1', 'f2'], 'fps': 8, 'playback_mode': 'loop'},
            trigger_action=lambda *args: None
        )
        # Mock speak on manager
        self.mgr.speak = lambda app, phrase: self.spoken.append(phrase)
        self.mgr.stop_speech = lambda app: self.spoken.append('__STOP__')
        self.mgr.is_tts_keep_loaded = lambda app=None: True

    def test_cold_load_offset_when_keep_loaded_false(self):
        """When keep_loaded is False, an offset of 14s is added to phase delays and timeout."""
        self.mgr.is_tts_keep_loaded = lambda app=None: False
        self.assertEqual(self.mgr.get_cold_load_offset(self.app), 14.0)

        action = {'id': 'cold_test', '_source_app_id': 'fuel', '_attention_waiting': True,
                  'attention_until_interaction': True}
        item = (action, 'Fuel', (0, 200, 255), 'Update', [], None)
        self.app.activity_queue.active = item
        self.mgr.start_session(self.app, item, now=0.0)
        # Session begins in silent waving mode (phase 0)
        self.assertEqual(len(self.spoken), 0)
        self.assertEqual(self.mgr.active_session['phase'], 0)

        # Baseline phase1 delay is 12s. With +14s cold offset, it needs 26s.
        # At t=20s, Phase 1 must not fire yet.
        self.mgr.tick(self.app, now=20.0)
        self.assertEqual(len(self.spoken), 0)

        # At t=27s, Phase 1 fires.
        self.mgr.tick(self.app, now=27.0)
        self.assertEqual(len(self.spoken), 1)

        # Speech finishes at t=35s
        self.mgr.tick(self.app, now=35.0)

        # Baseline phase2 delay is 28s. With +14s cold offset, it needs 42s.
        # At t=40s, Phase 2 must not fire yet.
        self.mgr.tick(self.app, now=40.0)
        self.assertEqual(len(self.spoken), 1)

        # At t=46s (elapsed >= 42s and silence >= 10s), Phase 2 fires.
        self.mgr.tick(self.app, now=46.0)
        self.assertEqual(len(self.spoken), 2)
        self.assertEqual(self.spoken[1], "Hey, it's me, your pal!")

        # Base timeout is 90s. With 2*cold_offset (+28s), timeout is 118s.
        # At t=95s, alert should NOT time out yet.
        self.mgr.tick(self.app, now=95.0)
        self.assertIsNotNone(self.mgr.active_session)

        # At t=119s, alert times out.
        self.mgr.tick(self.app, now=119.0)
        self.assertIsNone(self.mgr.active_session)
        self.assertTrue(any(ev[0] == 'attention_timed_out' for ev in self.events))

    def test_progressive_voice_ladder(self):
        """Test silent waving Phase 0, then Phase 1, Phase 2, Phase 3 and final timeout escalation."""
        action = {'id': 'fuel_alert', '_source_app_id': 'fuel', '_attention_waiting': True,
                  'attention_until_interaction': True, 'voice_phrase': 'Hey, fuel is down to {summary}!'}
        item = (action, 'Fuel Tracker', (0, 200, 255), '179.9c', [], None)

        self.app.activity_queue.active = item
        self.app.activity_queue.started = 0
        self.app.activity_queue.arrived = 0
        self.app.activity_queue.dwell = 1.0

        # Start session at t=0: Character waves arms silently first
        self.mgr.start_session(self.app, item, now=0.0)
        self.assertEqual(len(self.spoken), 0)
        self.assertEqual(self.mgr.active_session['phase'], 0)

        # At t=6s: Still waving arms silently (no speech yet)
        self.mgr.tick(self.app, now=6.0)
        self.assertEqual(len(self.spoken), 0)

        # At t=13s (elapsed >= 12s): Phase 1 fires!
        self.mgr.tick(self.app, now=13.0)
        self.assertEqual(len(self.spoken), 1)
        self.assertEqual(self.spoken[0], 'Hey, fuel is down to 179.9c!')
        self.assertEqual(self.mgr.active_session['phase'], 1)

        # At t=20s: Speech finished, starting silence timer
        self.mgr.tick(self.app, now=20.0)
        self.assertEqual(len(self.spoken), 1)

        # At t=31s (elapsed >= 28s and silence >= 10s): Phase 2 speech
        self.mgr.tick(self.app, now=31.0)
        self.assertEqual(len(self.spoken), 2)
        self.assertEqual(self.spoken[1], "Hey, it's me, your pal!")
        self.assertEqual(self.mgr.active_session['phase'], 2)

        # At t=35s: audio playback completes
        self.mgr.tick(self.app, now=35.0)
        self.assertEqual(len(self.spoken), 2)

        # At t=57s (elapsed >= 56s and silence >= 10s): Phase 3 speech
        self.mgr.tick(self.app, now=57.0)
        self.assertEqual(len(self.spoken), 3)
        self.assertEqual(self.spoken[2], "Hello? Over here!")
        self.assertEqual(self.mgr.active_session['phase'], 3)

        # At t=91s: Timeout! Character gives up and stops waving
        self.mgr.tick(self.app, now=91.0)
        self.assertIsNone(self.mgr.active_session)
        self.assertFalse(action.get('_attention_waiting'))
        self.assertTrue(any(ev[0] == 'attention_timed_out' for ev in self.events))
        self.assertEqual(self.app.target_animation, 'idle')
        self.assertTrue(any(ev[0] == 'attention_timed_out' for ev in self.events))

    def test_silent_waving_acknowledgement_prevents_speech(self):
        """If user taps the character during silent waving, the session completes with ZERO speech spoken."""
        action = {'id': 'wellness_alert', '_source_app_id': 'wellness', '_attention_waiting': True}
        item = (action, 'Wellness', (56, 189, 248), 'Hydrate!', [], None)
        self.app.activity_queue.active = item

        self.mgr.start_session(self.app, item, now=0.0)
        self.assertEqual(len(self.spoken), 0)

        # User sees the waving character at t=4s and taps screen
        self.mgr.tick(self.app, now=4.0)
        self.assertEqual(len(self.spoken), 0)

        self.mgr.acknowledge(self.app)
        self.assertIsNone(self.mgr.active_session)
        # Verify no speech was ever triggered
        self.assertEqual(len([s for s in self.spoken if s != '__STOP__']), 0)

    def test_voice_escalation_waits_while_speech_busy(self):
        """Phase escalation does not collide or speak while TTS synthesis or audio playback is busy."""
        action = {'id': 'order_alert', '_source_app_id': 'orders', '_attention_waiting': True}
        item = (action, 'Orders', (0, 200, 255), 'New order', [], None)
        self.app.activity_queue.active = item

        self.mgr.start_session(self.app, item, now=0.0)
        self.assertEqual(len(self.spoken), 0)

        # Phase 1 fires at t=13s
        self.mgr.tick(self.app, now=13.0)
        self.assertEqual(len(self.spoken), 1)

        # Simulate Piper still synthesizing or playing audio
        self.mgr.is_speech_busy = lambda app: True

        # Even past 30s, Phase 2 must NOT speak while speech is busy
        self.mgr.tick(self.app, now=32.0)
        self.assertEqual(len(self.spoken), 1)

        # Once speech completes and finishes
        self.mgr.is_speech_busy = lambda app: False
        self.mgr.tick(self.app, now=34.0)
        # Give buffer silence
        self.mgr.tick(self.app, now=46.0)
        self.assertEqual(len(self.spoken), 2)
        self.assertEqual(self.spoken[1], "Hey, it's me, your pal!")

    def test_presence_gating_and_deferred_delivery(self):
        """When user is absent, alert is deferred until return; stale alerts expire."""
        # User is away
        self.app.radar_nearby_present = False
        self.app.last_radar_nearby = {'targets': []}

        action = {'id': 'order_123', '_source_app_id': 'orders', '_attention_waiting': True,
                  'attention_until_interaction': True, '_received_at': time.time()}
        item = (action, 'Orders', (255, 100, 0), 'New order #123', [], None)

        self.assertTrue(self.mgr.should_defer_for_absence(self.app, action))
        self.mgr.defer_alert(self.app, item)
        self.assertEqual(len(self.mgr.deferred_alerts), 1)
        self.assertTrue(any(ev[0] == 'attention_deferred_for_presence' for ev in self.events))

        # While user still away, tick does nothing
        self.mgr.tick(self.app, now=10.0)
        self.assertEqual(len(self.mgr.deferred_alerts), 1)
        self.assertEqual(len(self.spoken), 0)

        # User walks up to the desk
        self.app.radar_nearby_present = True
        self.app.last_radar_nearby = {'targets': [{'x': 0, 'y': 1.2}]}

        self.mgr.tick(self.app, now=15.0)
        # Alert should be resumed into queue
        self.assertEqual(len(self.mgr.deferred_alerts), 0)
        self.assertEqual(len(self.app.activity_queue.items), 1)
        self.assertTrue(any(ev[0] == 'attention_deferred_resumed' for ev in self.events))

    def test_stale_alert_expires_after_ttl(self):
        """If user is away for hours, stale notification is silently purged and not alerted."""
        self.app.radar_nearby_present = False
        self.app.last_radar_nearby = {'targets': []}

        # Alert received 1000 seconds ago (> 900s limit)
        action = {'id': 'old_order', '_source_app_id': 'orders', '_attention_waiting': True,
                  '_received_at': time.time() - 1200}
        item = (action, 'Orders', (255, 100, 0), 'Old order', [], None)

        self.mgr.defer_alert(self.app, item)
        self.assertEqual(len(self.mgr.deferred_alerts), 1)

        # User returns
        self.app.radar_nearby_present = True
        self.mgr.tick(self.app, now=100.0)

        # Stale alert must be expired and discarded, NOT queued
        self.assertEqual(len(self.mgr.deferred_alerts), 0)
        self.assertEqual(len(self.app.activity_queue.items), 0)
        self.assertTrue(any(ev[0] == 'attention_deferred_expired' for ev in self.events))

    def test_user_walks_away_pauses_voice(self):
        """If user steps away mid-ladder, voice escalation is paused until they return."""
        action = {'id': 'fuel_alert', '_source_app_id': 'fuel', '_attention_waiting': True}
        item = (action, 'Fuel', (0, 200, 255), 'Fuel drop', [], None)
        self.app.activity_queue.active = item

        self.mgr.start_session(self.app, item, now=0.0)
        self.assertEqual(len(self.spoken), 0)

        # Phase 1 fires at t=13s
        self.mgr.tick(self.app, now=13.0)
        self.assertEqual(len(self.spoken), 1)
        # Finished audio
        self.mgr.tick(self.app, now=15.0)

        # User steps away
        self.app.radar_nearby_present = False
        self.app.last_radar_nearby = {'targets': []}

        # At t=31s (normally Phase 2): suppressed because user is not present
        self.mgr.tick(self.app, now=31.0)
        self.assertEqual(len(self.spoken), 1)

        # User returns at t=35s
        self.app.radar_nearby_present = True
        self.app.last_radar_nearby = {'targets': [{'x': 0, 'y': 1.0}]}
        self.mgr.tick(self.app, now=35.0)
        self.assertEqual(len(self.spoken), 2)
        self.assertEqual(self.spoken[1], "Hey, it's me, your pal!")

    def test_acknowledgement_cancels_ladder(self):
        """Tapping or pressing button acknowledges and cancels the voice ladder immediately."""
        action = {'id': 'test_alert', '_source_app_id': 'fuel', '_attention_waiting': True}
        item = (action, 'Fuel', (0, 200, 255), 'Fuel drop', [], None)
        self.app.activity_queue.active = item

        self.mgr.start_session(self.app, item)
        self.assertIsNotNone(self.mgr.active_session)

        # Acknowledge
        self.mgr.acknowledge(self.app)
        self.assertIsNone(self.mgr.active_session)
        self.assertIn('__STOP__', self.spoken)

    def test_voice_escalation_disabled_per_action(self):
        """An action with voice_escalation=False performs visual wave without TTS."""
        action = {'id': 'silent_alert', '_source_app_id': 'fuel', '_attention_waiting': True,
                  'voice_escalation': False}
        item = (action, 'Fuel', (0, 200, 255), 'Silent drop', [], None)
        self.app.activity_queue.active = item

        self.mgr.start_session(self.app, item)
        self.assertEqual(len(self.spoken), 0)
        self.assertFalse(self.mgr.active_session['voice_enabled'])

        self.mgr.tick(self.app, now=20.0)
        self.assertEqual(len(self.spoken), 0)

    def test_queue_tick_during_attention_timeout(self):
        """When an attention session times out inside queue.tick, activity_queue safely completes without TypeError."""
        self.app.attention_voice_manager = self.mgr
        self.app.is_sleeping = False
        self.app.edit_mode = False
        self.app.scene_journey = []
        self.app.journey_arriving = False
        self.app.rest_transition = None
        self.app.sequence_tick_limit = lambda seq: float("inf")
        action = {'id': 'fuel_timeout_test', '_source_app_id': 'fuel', '_attention_waiting': True,
                  'attention_until_interaction': True, 'duration_seconds': 6.0}
        item = (action, 'Fuel', (0, 200, 255), 'Update', [], None)
        self.app.activity_queue.enqueue(item)

        # Tick at t=0 to pop item, and tick at t=0.1 once arrived/settled
        self.app.activity_queue.tick(self.app, now=0.0)
        self.assertIsNotNone(self.app.activity_queue.active)
        self.app.activity_queue.tick(self.app, now=0.1)
        self.assertIsNotNone(self.mgr.active_session)

        # Advance to timeout t=120.0: tick should not raise TypeError
        self.app.activity_queue.tick(self.app, now=120.0)
        self.assertIsNone(self.app.activity_queue.active)
        self.assertIsNone(self.mgr.active_session)
        self.assertTrue(any(ev[0] == 'attention_timed_out' for ev in self.events))


if __name__ == '__main__':
    unittest.main()
