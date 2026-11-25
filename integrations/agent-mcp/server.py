"""Optional stdio MCP interface; Desk-Pal itself needs no MCP dependencies."""
import argparse
import os
from pathlib import Path
from typing import Literal
from bridge import AgentBridge


def build_server(bridge):
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('Desk-Pal Embodied Companion')

    @server.tool()
    def deskpal_get_capabilities() -> dict:
        """Dynamically discover Desk-Pal device profile, touchscreen display, Piper TTS voice,
        24GHz mmWave radar presence, available scenes, interaction spots, animations catalog,
        installed services, and agent etiquette guidelines.
        """
        return bridge.get_capabilities()

    @server.tool()
    def deskpal_get_world() -> dict:
        """Inspect real-time spatial world state: current scene, character position (x, y),
        facing direction, current animation, human radar presence, and all scene spots.
        """
        return bridge.get_world()

    @server.tool()
    def deskpal_puppeteer(scene: str = None, spot_id: str = None, x: float = None, y: float = None,
                          animation: str = None, facing: Literal['left', 'right'] = None,
                          speech: str = None, thought: str = None,
                          duration_seconds: float = 6.0, priority: bool = True) -> dict:
        """Directly pilot the character sprite across scenes, spots, or coordinates.

        Args:
            scene: Target scene to navigate to (e.g. 'cozy_study', 'resort_beach', 'video_store', 'apartment').
            spot_id: Named interaction spot to walk to (e.g. 'computer_desk', 'bookshelf', 'window', 'tiki_bar').
            x: Target screen X coordinate (0-1280).
            y: Target screen Y coordinate (0-720).
            animation: Animation to play upon arrival (e.g. 'typing', 'inspect', 'wave_arms', 'sitting_rest', 'window_look').
            facing: Direction to face ('left' or 'right').
            speech: Voice text to speak aloud via Piper TTS.
            thought: Comic thought bubble text to display above the sprite inside the world.
            duration_seconds: How long to perform/hold the action (default: 6.0).
            priority: If True, interrupts ambient wandering immediately.
        """
        return bridge.puppeteer(scene=scene, spot_id=spot_id, x=x, y=y, animation=animation,
                                facing=facing, speech=speech, thought=thought,
                                duration_seconds=duration_seconds, priority=priority)

    @server.tool()
    def deskpal_notify(title: str, message: str, layout: Literal['classic', 'dashboard', 'wellness'] = 'classic',
                       attention: bool = True, speech: str = None) -> dict:
        """Display an interactive full-screen modal card on the 1280x720 touchscreen.

        Args:
            title: Header title of the card (e.g. 'Build Passed', 'PR Review Ready').
            message: Body markdown or summary text.
            layout: Visual layout template: 'classic' (text with page counter), 'dashboard' (hero metric + tiles), 'wellness' (hydration + animated stretch).
            attention: If True, character waves arms and card waits for a physical touch tap to dismiss.
            speech: Optional voice announcement read aloud via Piper TTS.
        """
        return bridge.notify(title=title, message=message, layout=layout, attention=attention, speech=speech)

    @server.tool()
    def deskpal_speak(text: str) -> dict:
        """Speak a sentence aloud over the room speaker using on-device Piper Neural TTS."""
        return bridge.speak(text=text)

    @server.tool()
    def deskpal_get_presence() -> dict:
        """Query the 24GHz mmWave radar sensor to check if the human is sitting at their desk."""
        return bridge.get_presence()

    @server.tool()
    def deskpal_get_sensors() -> dict:
        """Inspect real-time environmental sensors and display sleep status (ambient LUX light level,
        24GHz mmWave radar presence, bedtime window, and active sleep/wake policy decisions).
        """
        return bridge.get_sensors()

    @server.tool()
    def deskpal_control_display(action: Literal['sleep', 'wake'] = 'wake') -> dict:
        """Put the physical touchscreen display into standby ('sleep') or wake it up ('wake')."""
        return bridge.control_display(action=action)

    @server.tool()
    def deskpal_travel_scene(scene: str) -> dict:
        """Trigger an animated walking journey between rooms (e.g. 'cozy_study', 'resort_beach')."""
        return bridge.travel_scene(scene=scene)

    @server.tool()
    def deskpal_report_activity(activity: Literal['started', 'researching', 'coding', 'completed', 'needs_attention', 'failed'],
                                task_id: str, message: str, occurrence_id: str) -> dict:
        """Report a task phase update for mapping to user-configured activity rules and button tickers."""
        return bridge.report(activity, task_id, message, occurrence_id)

    @server.tool()
    def deskpal_get_status() -> dict:
        """Read connectivity, global queue state/count and this adapter's last reported phase."""
        return bridge.status()

    @server.tool()
    def deskpal_dismiss_modal() -> dict:
        """Dismiss any active full-screen notification card or popup modal currently showing on screen."""
        return bridge.dismiss_modal()

    @server.tool()
    def deskpal_get_preview_frame() -> dict:
        """Capture a live screenshot/preview frame (1280x720 JPEG encoded as base64) of the current
        touchscreen display canvas to visually inspect character positioning, active props, or card overlays.
        """
        return bridge.get_preview_frame(as_base64=True)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deskpal', default=os.environ.get('DESKPAL_URL', 'http://127.0.0.1:7777'))
    parser.add_argument('--app-id', default=os.environ.get('DESKPAL_AGENT_ID', 'llm_agent'))
    parser.add_argument('--agent-name', default=os.environ.get('DESKPAL_AGENT_NAME', 'LLM agent'))
    parser.add_argument('--state-dir', default=os.environ.get('DESKPAL_AGENT_STATE_DIR', str(Path.home()/'.deskpal-agent')))
    args = parser.parse_args()
    # Hash the origin into the file name so multiple Desk-Pal installations remain separate.
    import hashlib
    identity = hashlib.sha256(args.deskpal.rstrip('/').encode()).hexdigest()[:16]
    state = Path(args.state_dir)/('deskpal-agent-'+args.app_id+'-'+identity+'.json')
    bridge = AgentBridge(args.deskpal, args.app_id, args.agent_name, state)
    build_server(bridge).run(transport='stdio')


if __name__ == '__main__':
    main()
