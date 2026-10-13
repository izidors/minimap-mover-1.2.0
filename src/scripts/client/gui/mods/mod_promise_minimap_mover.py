# -*- coding: utf-8 -*-
"""
Promise Minimap Mover 1.1.8

Controls:
    Ctrl + click on minimap
        Normal World of Tanks minimap action (ping, etc.).

    Ctrl + Shift + LMB + drag
        Move the minimap. A 5 px threshold separates a click from a drag.

Config (position + size):
    <preferences>/mods/promise/minimap_mover.cfg
    Format: offset_x offset_y size_index
"""
from __future__ import print_function

import logging
import math
import os

import BigWorld
import Keys

from gui import InputHandler
from helpers import getPreferencesDirPath
from gui.Scaleform.daapi.view.battle.shared.minimap.component import (
    MinimapComponent
)


# ===========================================================================
# Mod information
# ===========================================================================

__version__ = '1.2.1'
MOD_VERSION = __version__
MOD_NAME = 'MinimapMover'

_LOGGER = logging.getLogger('Promise.MinimapMover')

# Optional ModsSettingsAPI integration. Position/size remain in the original cfg.
MSA_LINKAGE = 'promiseMinimapMover'
_MSA_REGISTERED = False
_MSA_RETRY = None
_enabled = True



def log(message):
    _LOGGER.info('[%s %s] %s', MOD_NAME, MOD_VERSION, message)


# ===========================================================================
# Constants
# ===========================================================================

POLL_INTERVAL = 0.02
DRAG_THRESHOLD = 5.0
REFRESH_DELAY = 0.05
SIZE_WATCH_INTERVAL = 0.5


# ===========================================================================
# State
# ===========================================================================

_minimap = None

_offset_x = 0.0
_offset_y = 0.0
_base_x = None
_base_y = None
_base_locked = False

_saved_size = None      # from cfg
_size_watch_callback = None
_size_watch_ready = False
_battle_size = None     # frozen once per battle before any as_setSize

_poll_callback = None
_refresh_callback = None
_apply_callbacks = []

_mouse_was_down = False
_drag_candidate = False
_dragging = False
_drag_start_x = None
_drag_start_y = None
_last_x = None
_last_y = None

_installed = False
_original_populate = None
_original_dispose = None
_size_hook_class = None
_size_hook_original = None
_size_hook_attempted = False
_internal_size_call = False
_last_user_resize_key_time = -1000.0


# ===========================================================================
# Configuration
# ===========================================================================

def _enabled_path():
    folder = _get_config_directory()
    return os.path.join(folder, 'minimap_mover_enabled.json') if folder else None


def load_enabled():
    global _enabled
    path = _enabled_path()
    if not path or not os.path.isfile(path):
        return
    try:
        import json
        with open(path, 'r') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _enabled = bool(data.get('enabled', True))
    except Exception:
        _LOGGER.exception('Unable to load enabled setting')


def save_enabled():
    path = _enabled_path()
    if not path:
        return
    try:
        import json
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path, 'w') as fh:
            json.dump({'enabled': _enabled}, fh)
    except Exception:
        _LOGGER.exception('Unable to save enabled setting')


def _on_msa_changed(*args):
    global _enabled
    # ModsSettingsAPI implementations may call (linkage, settings) or (settings).
    settings = None
    if len(args) >= 2 and isinstance(args[1], dict):
        if args[0] != MSA_LINKAGE:
            return
        settings = args[1]
    elif len(args) >= 1 and isinstance(args[0], dict):
        settings = args[0]
    if settings is None or 'enabled' not in settings:
        return
    new_value = bool(settings['enabled'])
    if new_value == _enabled:
        return
    _enabled = new_value
    save_enabled()
    if not _enabled:
        cancel_poll()
        cancel_size_watch()
        cancel_refresh()
        cancel_apply_callbacks()
        reset_drag_state()
    log('Settings enabled=%s (full layout change on next battle)' % _enabled)


def register_mods_settings():
    global _MSA_REGISTERED
    if _MSA_REGISTERED:
        return True
    # Prefer the Aslain menu actually installed in this game client.
    try:
        from gui.aslainMenu import g_modsSettingsApi, templates
        template = {
            'modDisplayName': 'Promise Minimap Mover',
            'column1': [templates.createCheckbox('Enable Minimap Mover', 'enabled', bool(_enabled))],
            'column2': []
        }
        g_modsSettingsApi.setModTemplate(MSA_LINKAGE, template, _on_msa_changed)
        _MSA_REGISTERED = True
        log('Aslain Mod Menu registered')
        return True
    except Exception:
        _LOGGER.debug('Aslain Mod Menu registration unavailable', exc_info=True)
    return False


def retry_msa_registration():
    global _MSA_RETRY
    _MSA_RETRY = None
    if not _installed:
        return
    if not register_mods_settings():
        _MSA_RETRY = BigWorld.callback(2.0, retry_msa_registration)


def _get_config_directory():
    try:
        base = getPreferencesDirPath()
        if not base:
            _LOGGER.error('getPreferencesDirPath() returned empty path')
            return None
        return os.path.join(base, 'mods', 'promise')
    except Exception:
        _LOGGER.exception('Unable to determine preferences directory')
    return None


def _get_config_path():
    folder = _get_config_directory()
    if folder is None:
        return None
    return os.path.join(folder, 'minimap_mover.cfg')


def _is_finite(value):
    try:
        return not (math.isnan(value) or math.isinf(value))
    except Exception:
        return False


def load_offset():
    global _offset_x, _offset_y, _saved_size
    _offset_x = 0.0
    _offset_y = 0.0
    _saved_size = None

    path = _get_config_path()
    if not path:
        return
    if not os.path.isfile(path):
        log('No saved position yet')
        return

    try:
        f = open(path, 'r')
        try:
            data = f.read().strip()
        finally:
            f.close()

        parts = data.replace(',', ' ').split()
        if len(parts) < 2:
            log('Invalid config; using default position')
            return

        ox = float(parts[0])
        oy = float(parts[1])
        if not _is_finite(ox) or not _is_finite(oy):
            log('Non-finite offset; using default position')
            return

        _offset_x = ox
        _offset_y = oy

        if len(parts) >= 3:
            try:
                sz = int(float(parts[2]))
                if 0 <= sz <= 5:
                    _saved_size = sz
            except Exception:
                pass

        log(
            'Loaded offset %.1f %.1f size=%s'
            % (_offset_x, _offset_y, _saved_size)
        )
    except Exception:
        _offset_x = 0.0
        _offset_y = 0.0
        _saved_size = None
        _LOGGER.exception('Unable to load saved minimap position')


def save_offset():
    global _saved_size
    path = _get_config_path()
    if not path:
        return

    size = _battle_size
    if size is None:
        size = _saved_size
    if size is None:
        size = read_minimap_size_from_settings()

    _saved_size = int(size)
    folder = os.path.dirname(path)
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)

        temporary = path + '.tmp'
        f = open(temporary, 'w')
        try:
            f.write(
                '%.2f %.2f %d\n'
                % (_offset_x, _offset_y, int(size))
            )
        finally:
            f.close()

        if os.path.isfile(path):
            os.remove(path)
        os.rename(temporary, path)
        log(
            'Saved offset %.1f %.1f size=%s'
            % (_offset_x, _offset_y, size)
        )
    except Exception:
        _LOGGER.exception('Unable to save minimap position')


# ===========================================================================
# Input helpers
# ===========================================================================

def _key_down(key):
    try:
        return BigWorld.isKeyDown(key)
    except Exception:
        return False


def ctrl_down():
    return _key_down(Keys.KEY_LCONTROL) or _key_down(Keys.KEY_RCONTROL)


def shift_down():
    return _key_down(Keys.KEY_LSHIFT) or _key_down(Keys.KEY_RSHIFT)


def modifiers_active():
    return ctrl_down() and shift_down()


def is_lmb_held():
    for name in ('KEY_LEFTMOUSE', 'KEY_MOUSE0', 'KEY_MOUSELEFT'):
        key = getattr(Keys, name, None)
        if key is None:
            continue
        try:
            if BigWorld.isKeyDown(key):
                return True
        except Exception:
            pass
    return False


# ===========================================================================
# Screen / mouse
# ===========================================================================

def get_screen_size():
    try:
        return BigWorld.screenSize()
    except Exception:
        pass
    try:
        import GUI
        return GUI.screenResolution()
    except Exception:
        pass
    return 1920, 1080


def get_mouse_pos():
    try:
        pos = BigWorld.getCursorPos()
        if pos is not None:
            return float(pos[0]), float(pos[1])
    except Exception:
        pass
    try:
        import GUI
        pos = GUI.mcursor().position
        x = float(pos[0])
        y = float(pos[1])
        sw, sh = get_screen_size()
        if -1.5 <= x <= 1.5 and -1.5 <= y <= 1.5:
            x = (x + 1.0) * 0.5 * sw
            y = (1.0 - y) * 0.5 * sh
        return x, y
    except Exception:
        pass
    return None


# ===========================================================================
# Minimap access
# ===========================================================================

def get_flash():
    if _minimap is None:
        return None
    try:
        return _minimap.flashObject
    except Exception:
        return None


def get_display_info():
    flash = get_flash()
    if flash is None:
        return None
    try:
        return flash.getDisplayInfo()
    except Exception:
        return None


def get_minimap_size_pixels():
    if _minimap is not None:
        try:
            size = _minimap._getMinimapSize()
            if size is not None and len(size) >= 2:
                w, h = float(size[0]), float(size[1])
                if w > 0.0 and h > 0.0:
                    return w, h
        except Exception:
            pass

    info = get_display_info()
    if info is not None:
        try:
            w = float(info.width)
            h = float(info.height)
            if w > 0.0 and h > 0.0:
                return w, h
        except Exception:
            pass

    flash = get_flash()
    if flash is not None:
        try:
            w = float(flash.width)
            h = float(flash.height)
            if w > 0.0 and h > 0.0:
                return w, h
        except Exception:
            pass
    return None


def clamp_offset_to_screen():
    global _offset_x, _offset_y
    if not _base_locked or _base_x is None or _base_y is None:
        return

    sw, sh = get_screen_size()
    size = get_minimap_size_pixels()
    if size is None:
        w, h = 200.0, 200.0
    else:
        w, h = size

    target_x = _base_x + _offset_x
    target_y = _base_y + _offset_y

    min_x = -w * 0.75
    min_y = -h * 0.75
    max_x = sw - w * 0.25
    max_y = sh - h * 0.25

    clamped_x = max(min_x, min(max_x, target_x))
    clamped_y = max(min_y, min(max_y, target_y))

    _offset_x = clamped_x - _base_x
    _offset_y = clamped_y - _base_y


# ===========================================================================
# Position
# ===========================================================================

def apply_position(x, y):
    flash = get_flash()
    if flash is None:
        return False
    try:
        info = flash.getDisplayInfo()
        info.x = float(x)
        info.y = float(y)
        flash.setDisplayInfo(info)
        return True
    except Exception:
        _LOGGER.exception('Unable to move minimap')
    return False


def lock_base_from_layout():
    global _base_x, _base_y, _base_locked
    if _base_locked:
        return True
    info = get_display_info()
    if info is None:
        return False
    try:
        _base_x = float(info.x)
        _base_y = float(info.y)
        _base_locked = True
        log('Base position %.1f %.1f' % (_base_x, _base_y))
        return True
    except Exception:
        _LOGGER.exception('Unable to determine original minimap position')
    return False


def reapply_offset():
    if not _base_locked or _base_x is None or _base_y is None:
        return
    apply_position(_base_x + _offset_x, _base_y + _offset_y)


def move_minimap_by(dx, dy):
    global _offset_x, _offset_y
    if not _base_locked:
        if not lock_base_from_layout():
            return
    _offset_x += float(dx)
    _offset_y += float(dy)
    reapply_offset()


# ===========================================================================
# Size / refresh
# ===========================================================================

def read_minimap_size_from_settings():
    try:
        from account_helpers.settings_core.settings_constants import GAME
        from helpers import dependency
        from skeletons.account_helpers.settings_core import ISettingsCore

        settings_core = dependency.instance(ISettingsCore)
        value = settings_core.getSetting(GAME.MINIMAP_SIZE)
        if isinstance(value, (int, long)):
            return int(value)
    except Exception:
        _LOGGER.exception('Unable to read minimap size setting')
    return 2


def write_minimap_size_to_settings(index):
    try:
        from account_helpers.settings_core.settings_constants import GAME
        from helpers import dependency
        from skeletons.account_helpers.settings_core import ISettingsCore

        settings_core = dependency.instance(ISettingsCore)
        index = int(index)

        if hasattr(settings_core, 'applySetting'):
            settings_core.applySetting(GAME.MINIMAP_SIZE, index)
        elif hasattr(settings_core, 'setSetting'):
            settings_core.setSetting(GAME.MINIMAP_SIZE, index)

        for name in ('applyStorages', 'save', 'forceSave'):
            fn = getattr(settings_core, name, None)
            if not callable(fn):
                continue
            try:
                if name == 'applyStorages':
                    fn(False)
                else:
                    fn()
                break
            except Exception:
                pass
        return True
    except Exception:
        _LOGGER.exception('Unable to write minimap size setting')
    return False


# Class-level hooks on the concrete ClassicMinimapComponent (diagnostic only).
# Do not hook PyGFxDisplayObject: it does not expose as_setSize.
_size_hook_originals = {}
_size_hook_wrappers = {}


def record_user_minimap_size(index):
    if not _enabled:
        return
    global _battle_size
    _battle_size = int(index)
    save_offset()
    log('USER SIZE SAVED index=%s' % index)


def install_size_diagnostic_hook():
    global _size_hook_class
    if _minimap is None:
        return
    cls = type(_minimap)
    if _size_hook_class is cls:
        return
    if _size_hook_class is not None:
        remove_size_diagnostic_hook()
    _size_hook_class = cls
    for name in ('applyNewSize', '_processMinimapSize', 'as_setSizeS'):
        original = getattr(cls, name, None)
        if not callable(original):
            log('METHOD HOOK unavailable %s' % name)
            continue
        # Preserve any existing patches (including centered minimap).
        def make_wrapper(method_name, method):
            def wrapper(self, *args, **kwargs):
                result = method(self, *args, **kwargs)
                if (_enabled and method_name == 'as_setSizeS' and self is _minimap and
                        not _internal_size_call and _size_watch_ready and args):
                    try:
                        now = BigWorld.time()
                        size = float(args[0])
                        index = int(round(size))
                        if (now - _last_user_resize_key_time <= 0.8 and
                                abs(size - index) < 0.001 and 0 <= index <= 5 and
                                index != _battle_size):
                            record_user_minimap_size(index)
                    except Exception:
                        _LOGGER.exception('Unable to capture actual minimap size')
                return result
            return wrapper
        wrapped = make_wrapper(name, original)
        try:
            setattr(cls, name, wrapped)
            _size_hook_originals[name] = original
            _size_hook_wrappers[name] = wrapped
            log('METHOD HOOK installed %s original=%r module=%r' %
                (name, original, getattr(original, '__module__', None)))
        except Exception as exc:
            log('METHOD HOOK failed %s error=%r' % (name, exc))


def remove_size_diagnostic_hook():
    global _size_hook_class
    cls = _size_hook_class
    if cls is not None:
        for name, original in _size_hook_originals.items():
            try:
                if getattr(cls, name, None) is _size_hook_wrappers.get(name):
                    setattr(cls, name, original)
            except Exception:
                _LOGGER.exception('Unable to restore size method %s', name)
    _size_hook_originals.clear()
    _size_hook_wrappers.clear()
    _size_hook_class = None


_last_diagnostic_key_time = 0.0


def _safe_method_probe(component, name):
    if component is None:
        return 'no component'
    try:
        method = getattr(component, name, None)
        if not callable(method):
            return 'not callable'
        return repr(method())[:240]
    except Exception as exc:
        return 'error:%s' % (str(exc)[:160],)


def _size_snapshot():
    try:
        component = _minimap
        flash = get_flash()
        info = get_display_info()
        return ('getMinimapSize=%s pixels=%r display=%r '
                'flash_as_setSize=%s component_as_setSizeS=%s '
                'setting=%r saved=%r battle=%r' % (
                    _safe_method_probe(component, '_getMinimapSize'),
                    get_minimap_size_pixels(),
                    None if info is None else (getattr(info, 'width', None), getattr(info, 'height', None)),
                    bool(flash is not None and hasattr(flash, 'as_setSize')),
                    bool(component is not None and hasattr(component, 'as_setSizeS')),
                    read_minimap_size_from_settings(), _saved_size, _battle_size))
    except Exception as exc:
        return 'snapshot_error=%r' % (exc,)


def _log_resize_diagnostic(key):
    global _last_diagnostic_key_time
    if key not in (getattr(Keys, 'KEY_EQUALS', -999), getattr(Keys, 'KEY_MINUS', -998),
                   getattr(Keys, 'KEY_ADD', -997), getattr(Keys, 'KEY_SUBTRACT', -996)):
        return
    try:
        now = BigWorld.time()
        if now - _last_diagnostic_key_time < 0.12:
            return
        _last_diagnostic_key_time = now
    except Exception:
        pass
    log('SIZE BEFORE key=%s %s' % (key, _size_snapshot()))
    def after():
        if _minimap is not None:
            log('SIZE AFTER key=%s %s' % (key, _size_snapshot()))
    BigWorld.callback(0.35, after)


def set_minimap_display_size(index):
    global _internal_size_call
    install_size_diagnostic_hook()
    flash = get_flash()
    if flash is None:
        return False
    try:
        if hasattr(flash, 'as_setSize'):
            _internal_size_call = True
            try:
                flash.as_setSize(int(index))
            finally:
                _internal_size_call = False
            return True
    except Exception:
        _LOGGER.exception('Unable to set minimap display size')
    return False


def freeze_battle_size():
    """
    Capture the size we will restore for this battle.
    Must run before any as_setSize, otherwise settings may already be wrong.
    """
    global _battle_size
    if _battle_size is not None:
        return _battle_size

    live = read_minimap_size_from_settings()

    # The configuration is authoritative at battle startup.
    # Later, the size watcher accepts deliberate in-battle changes.
    if _saved_size is not None:
        _battle_size = int(_saved_size)
    else:
        _battle_size = int(live)

    log('Battle minimap size frozen to %s' % _battle_size)
    return _battle_size


def cancel_refresh():
    global _refresh_callback
    if _refresh_callback is None:
        return
    try:
        BigWorld.cancelCallback(_refresh_callback)
    except Exception:
        pass
    _refresh_callback = None


def refresh_minimap():
    """
    Nudge size once to clear the black hole, then restore the frozen size
    into both Flash and the settings plugin (two passes).
    """
    global _refresh_callback
    if _minimap is None:
        return

    cancel_refresh()

    preferred = freeze_battle_size()
    temporary = preferred - 1 if preferred > 0 else preferred + 1

    log(
        'Refreshing minimap %s -> %s -> %s'
        % (preferred, temporary, preferred)
    )

    set_minimap_display_size(temporary)
    reapply_offset()

    def restore_pass(pass_id):
        global _refresh_callback
        _refresh_callback = None
        if _minimap is None:
            return

        set_minimap_display_size(preferred)
        write_minimap_size_to_settings(preferred)
        reapply_offset()
        log('Minimap size restore pass %s -> %s' % (pass_id, preferred))

        if pass_id == 1:
            _refresh_callback = BigWorld.callback(
                0.08,
                lambda: restore_pass(2)
            )

    _refresh_callback = BigWorld.callback(
        REFRESH_DELAY,
        lambda: restore_pass(1)
    )


def cancel_size_watch():
    global _size_watch_callback, _size_watch_ready
    if _size_watch_callback is not None:
        try:
            BigWorld.cancelCallback(_size_watch_callback)
        except Exception:
            pass
    _size_watch_callback = None
    _size_watch_ready = False


def watch_minimap_size():
    # Size is captured by as_setSizeS on actual user resize input.
    return


def begin_size_watch():
    global _size_watch_ready
    _size_watch_ready = True


# ===========================================================================
# Callback management
# ===========================================================================

def cancel_poll():
    global _poll_callback
    if _poll_callback is None:
        return
    try:
        BigWorld.cancelCallback(_poll_callback)
    except Exception:
        pass
    _poll_callback = None


def cancel_apply_callbacks():
    global _apply_callbacks
    callbacks = list(_apply_callbacks)
    _apply_callbacks = []
    for callback_id in callbacks:
        try:
            BigWorld.cancelCallback(callback_id)
        except Exception:
            pass


def schedule_apply(delay, tag):
    holder = [None]

    def callback():
        callback_id = holder[0]
        try:
            if callback_id in _apply_callbacks:
                _apply_callbacks.remove(callback_id)
        except Exception:
            pass

        if _minimap is None:
            return
        if not lock_base_from_layout():
            return

        freeze_battle_size()
        clamp_offset_to_screen()
        reapply_offset()
        log(
            '[%s] position %.1f %.1f'
            % (tag, _base_x + _offset_x, _base_y + _offset_y)
        )

        if tag == 'initial':
            # Restore saved size even when the minimap was never moved.
            refresh_minimap()
        elif tag == 'late':
            # Wait until the initial refresh has completed before observing
            # user changes, so our own size writes are not misidentified.
            begin_size_watch()

    callback_id = BigWorld.callback(delay, callback)
    holder[0] = callback_id
    _apply_callbacks.append(callback_id)


# ===========================================================================
# Drag state
# ===========================================================================

def reset_drag_state():
    global _mouse_was_down, _drag_candidate, _dragging
    global _drag_start_x, _drag_start_y, _last_x, _last_y
    _mouse_was_down = False
    _drag_candidate = False
    _dragging = False
    _drag_start_x = None
    _drag_start_y = None
    _last_x = None
    _last_y = None


def begin_drag_candidate(mouse_x, mouse_y):
    global _drag_candidate, _drag_start_x, _drag_start_y, _last_x, _last_y

    # No hit-test: DisplayInfo and cursor space disagree on this client.
    # Ctrl+Shift is the gate; DRAG_THRESHOLD separates click from drag.
    _drag_candidate = True
    _drag_start_x = mouse_x
    _drag_start_y = mouse_y
    _last_x = mouse_x
    _last_y = mouse_y
    log('Drag candidate at %.0f %.0f' % (mouse_x, mouse_y))
    return True


def finish_drag():
    global _dragging, _drag_candidate
    global _drag_start_x, _drag_start_y, _last_x, _last_y

    was_dragging = _dragging
    _dragging = False
    _drag_candidate = False
    _drag_start_x = None
    _drag_start_y = None
    _last_x = None
    _last_y = None

    if not was_dragging:
        return

    clamp_offset_to_screen()
    reapply_offset()
    save_offset()
    refresh_minimap()
    log('Drag finished')


# ===========================================================================
# Mouse polling
# ===========================================================================

def start_poll():
    global _poll_callback
    if _poll_callback is not None:
        return
    _poll_callback = BigWorld.callback(POLL_INTERVAL, poll_mouse)


def poll_mouse():
    global _poll_callback, _mouse_was_down, _dragging, _last_x, _last_y

    _poll_callback = None

    if _minimap is None:
        return

    if not modifiers_active():
        if _dragging:
            finish_drag()
        else:
            reset_drag_state()
        return

    position = get_mouse_pos()
    if position is None:
        start_poll()
        return

    mouse_x, mouse_y = position
    mouse_down = is_lmb_held()

    if mouse_down and not _mouse_was_down:
        begin_drag_candidate(mouse_x, mouse_y)

    elif mouse_down and _mouse_was_down:
        if _drag_candidate:
            if not _dragging:
                dx = mouse_x - _drag_start_x
                dy = mouse_y - _drag_start_y
                if (dx * dx + dy * dy) >= (DRAG_THRESHOLD * DRAG_THRESHOLD):
                    _dragging = True
                    _last_x = mouse_x
                    _last_y = mouse_y
                    log('Drag started %.0f %.0f' % (mouse_x, mouse_y))
            else:
                dx = mouse_x - _last_x
                dy = mouse_y - _last_y
                if abs(dx) > 0.01 or abs(dy) > 0.01:
                    move_minimap_by(dx, dy)
                _last_x = mouse_x
                _last_y = mouse_y

    elif not mouse_down and _mouse_was_down:
        if _dragging:
            finish_drag()
        else:
            reset_drag_state()

    _mouse_was_down = mouse_down
    start_poll()


# ===========================================================================
# Keyboard
# ===========================================================================


def on_key_event(event):
    global _last_user_resize_key_time
    if not _enabled:
        return False
    try:
        key = event.key
        if _minimap is not None and key in (
                getattr(Keys, 'KEY_EQUALS', -999), getattr(Keys, 'KEY_MINUS', -998),
                getattr(Keys, 'KEY_ADD', -997), getattr(Keys, 'KEY_SUBTRACT', -996)):
            _last_user_resize_key_time = BigWorld.time()
        if key not in (
            Keys.KEY_LCONTROL,
            Keys.KEY_RCONTROL,
            Keys.KEY_LSHIFT,
            Keys.KEY_RSHIFT
        ):
            return False

        if modifiers_active():
            start_poll()
        else:
            if _dragging:
                finish_drag()
            else:
                reset_drag_state()
            cancel_poll()
    except Exception:
        _LOGGER.exception('Keyboard handler failed')
    return False


# ===========================================================================
# Battle lifecycle
# ===========================================================================

def teardown_battle():
    global _minimap, _base_x, _base_y, _base_locked, _battle_size
    cancel_poll()
    cancel_size_watch()
    cancel_refresh()
    cancel_apply_callbacks()
    reset_drag_state()
    _minimap = None
    _base_x = None
    _base_y = None
    _base_locked = False
    _battle_size = None


def _populate_wrapper(self):
    teardown_battle()
    _original_populate(self)
    if not _enabled:
        return
    try:
        global _minimap, _base_x, _base_y, _base_locked, _battle_size
        _minimap = self
        _base_x = None
        _base_y = None
        _base_locked = False
        _battle_size = None
        load_offset()
        log('Minimap registered; size methods: _getMinimapSize=%r _processMinimapSize=%r applyNewSize=%r as_setSizeS=%r' % (getattr(self, '_getMinimapSize', None), getattr(self, '_processMinimapSize', None), getattr(self, 'applyNewSize', None), getattr(self, 'as_setSizeS', None)))
        install_size_diagnostic_hook()
        # Freeze size before any refresh can call as_setSize.
        BigWorld.callback(0.15, freeze_battle_size)
        schedule_apply(0.25, 'initial')
        schedule_apply(1.0, 'late')
    except Exception:
        _LOGGER.exception('Minimap populate hook failed')


def _dispose_wrapper(self):
    # Do not overwrite the observed size with the stale settings value (2).
    try:
        teardown_battle()
    except Exception:
        _LOGGER.exception('Battle cleanup failed')
    if _original_dispose is not None:
        return _original_dispose(self)


# ===========================================================================
# Install / uninstall
# ===========================================================================

def init():
    global _installed, _original_populate, _original_dispose
    if _installed:
        return
    try:
        load_enabled()
        _original_populate = MinimapComponent._populate
        MinimapComponent._populate = _populate_wrapper

        if hasattr(MinimapComponent, '_dispose'):
            _original_dispose = MinimapComponent._dispose
            MinimapComponent._dispose = _dispose_wrapper

        InputHandler.g_instance.onKeyDown += on_key_event
        InputHandler.g_instance.onKeyUp += on_key_event

        _installed = True
        retry_msa_registration()
        log('Loaded; enabled=%s' % _enabled)
    except Exception:
        _LOGGER.exception('Unable to install MinimapMover')


def fini():
    global _installed, _original_populate, _original_dispose, _MSA_RETRY
    if not _installed:
        return

    if _MSA_RETRY is not None:
        try:
            BigWorld.cancelCallback(_MSA_RETRY)
        except Exception:
            pass
        _MSA_RETRY = None
    teardown_battle()
    remove_size_diagnostic_hook()

    try:
        InputHandler.g_instance.onKeyDown -= on_key_event
    except Exception:
        pass
    try:
        InputHandler.g_instance.onKeyUp -= on_key_event
    except Exception:
        pass

    try:
        if (
            _original_populate is not None and
            MinimapComponent._populate is _populate_wrapper
        ):
            MinimapComponent._populate = _original_populate
    except Exception:
        pass

    try:
        if (
            _original_dispose is not None and
            getattr(MinimapComponent, '_dispose', None) is _dispose_wrapper
        ):
            MinimapComponent._dispose = _original_dispose
    except Exception:
        pass

    _installed = False
    log('Unloaded')


init()