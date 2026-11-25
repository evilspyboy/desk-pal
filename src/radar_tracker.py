"""Backend radar target tracker with jump rejection and dropout hold.

Stabilizes RD-03D target reports by:
1. Suppressing transient multipath/reflection spikes (>600mm jump lasting <500ms).
2. Bridging micro-dropout intervals (1-2s) when a seated user remains motionless.
3. Allowing genuine sustained movement and relocation after confirmation.
"""
import math


class RadarTracker:
    def __init__(self, jump_threshold_mm=600, jump_confirm_seconds=0.5,
                 hold_dropout_seconds=2.5, smoothing_alpha=0.3):
        self.jump_threshold_mm = jump_threshold_mm
        self.jump_confirm_seconds = jump_confirm_seconds
        self.hold_dropout_seconds = hold_dropout_seconds
        self.smoothing_alpha = smoothing_alpha

        # Tracks indexed by slot (1..3)
        self.tracks = {}

    def reset(self):
        self.tracks.clear()

    @staticmethod
    def _ensure_metrics(t):
        if 'distance_mm' not in t:
            t['distance_mm'] = round(math.hypot(t.get('x_mm', 0), t.get('y_mm', 0)))
        if 'angle_deg' not in t:
            t['angle_deg'] = round(math.degrees(math.atan2(t.get('x_mm', 0), t.get('y_mm', 0))), 1)
        return t

    @staticmethod
    def _distance(t1, t2):
        return math.hypot(t1['x_mm'] - t2['x_mm'], t1['y_mm'] - t2['y_mm'])

    def update(self, raw_targets, now):
        """Update tracker with incoming raw targets for the current frame.
        
        raw_targets: list of target dicts from decode_frame
        now: current timestamp (float, seconds)
        
        Returns: list of stabilized target dicts
        """
        active_slots = set()
        stabilized = []

        # Process each detected target by its slot
        for cand_raw in raw_targets:
            cand = self._ensure_metrics(dict(cand_raw))
            slot = cand.get('slot', 1)
            active_slots.add(slot)
            track = self.tracks.get(slot)

            if track is None or track.get('accepted') is None:
                # Initial detection for this slot
                track = {
                    'accepted': dict(cand),
                    'last_seen': now,
                    'pending_jump': None,
                    'held': False,
                    'status': 'initial'
                }
                self.tracks[slot] = track
                stabilized.append(dict(track['accepted'], tracking_status='initial'))
                continue

            accepted = track['accepted']
            jump_dist = self._distance(cand, accepted)

            if jump_dist <= self.jump_threshold_mm:
                # Normal motion or consistent position
                track['pending_jump'] = None
                track['last_seen'] = now
                track['held'] = False
                track['status'] = 'tracking'

                # Apply light smoothing to steady jitter while tracking
                alpha = self.smoothing_alpha
                smooth_x = round((1 - alpha) * accepted['x_mm'] + alpha * cand['x_mm'])
                smooth_y = round((1 - alpha) * accepted['y_mm'] + alpha * cand['y_mm'])
                smooth_dist = round(math.hypot(smooth_x, smooth_y))
                smooth_angle = round(math.degrees(math.atan2(smooth_x, smooth_y)), 1)

                accepted.update(cand, x_mm=smooth_x, y_mm=smooth_y,
                                distance_mm=smooth_dist, angle_deg=smooth_angle)
                stabilized.append(dict(accepted, tracking_status='tracking'))
            else:
                # Target jumped > jump_threshold_mm (possible multipath reflection)
                pending = track.get('pending_jump')
                if pending is None or self._distance(cand, pending['target']) > 200:
                    track['pending_jump'] = {'target': dict(cand), 'since': now}
                    pending = track['pending_jump']

                if now - pending['since'] >= self.jump_confirm_seconds:
                    # New position held consistently for >= confirm threshold: accept relocation
                    track['accepted'] = dict(cand)
                    track['pending_jump'] = None
                    track['last_seen'] = now
                    track['held'] = False
                    track['status'] = 'reacquired'
                    stabilized.append(dict(track['accepted'], tracking_status='reacquired'))
                else:
                    # Transient jump in progress: hold previous accepted position
                    if now - track['last_seen'] <= self.hold_dropout_seconds:
                        retained = dict(accepted, speed_cm_s=0, tracking_status='jump_hold')
                        stabilized.append(retained)
                    else:
                        # Hold expired while waiting for jump: accept candidate
                        track['accepted'] = dict(cand)
                        track['pending_jump'] = None
                        track['last_seen'] = now
                        track['status'] = 'tracking'
                        stabilized.append(dict(track['accepted'], tracking_status='tracking'))

        # Check existing tracks that had no target in this frame (dropout)
        for slot, track in list(self.tracks.items()):
            if slot not in active_slots:
                if track.get('accepted') is not None:
                    if now - track['last_seen'] <= self.hold_dropout_seconds:
                        # Within dropout grace: hold last known target
                        retained = dict(track['accepted'], speed_cm_s=0, tracking_status='dropout_hold')
                        stabilized.append(retained)
                    else:
                        # Dropout grace expired: target has genuinely disappeared
                        del self.tracks[slot]

        # Sort targets by slot
        stabilized.sort(key=lambda t: t.get('slot', 1))
        return stabilized
