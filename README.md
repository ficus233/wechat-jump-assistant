# WeChat Jump Assistant for Windows

[English](README.md) | [简体中文](README.zh-CN.md)

An open-source Python assistant for the Jump Jump (跳一跳) mini program in WeChat for Windows. It uses normal screen capture and mouse input to detect platforms, calibrate press duration, and automate jumps.

## Features

- Piece contact-point and platform-top detection with OpenCV.
- White landing-marker centroid detection, shadow filtering, and textured-surface recovery.
- Whole-platform grouping for Rubik-style tiles and striped-roof recognition.
- Separate left/right calibration with camera-motion compensation and validated rolling linear models.
- Edge-landing recovery, independent global hotkeys, a control panel, and screenshot debugging.
- Per-jump timing, displacement records, and regression fixtures.

The assistant does not use ADB, client injection, memory access, network modification, or leaderboard manipulation.

## Requirements

- Windows 11 and Python 3.11 or later, including pip and Tcl/Tk.
- WeChat for Windows with the Jump Jump mini program open.
- Dependencies listed in [requirements.txt](requirements.txt): OpenCV, NumPy, mss, PyAutoGUI, and Pillow.

## Quick Start

1. Install Python and open the game in WeChat.
2. Double-click `start.bat` to open the control panel. The launcher creates a virtual environment and installs dependencies on first use.
3. Use `background.bat` for background operation, or `debug.bat` for the annotated screenshot and calibration interface.
4. Press **F9** to resume, **F10** to pause, and **F7** to exit the background worker.

The game must receive foreground input. Exceptions and cancellation release the mouse button.

The bundled configuration was measured on one Windows 11 setup: a **1077 × 1040 physical-pixel client area**, **120 DPI**, and canvas ROI `[520, 250, 550, 700]`. Startup attempts to restore the measured client size. For other layouts or DPI settings, reselect the canvas, inspect detection, and recalibrate. These values are not universal game physics.

## Tests

Run from the project directory on Windows:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -v
```

The test suite contains **64 tests**, including real failure-frame replay, mirrored directions, 3,200 simulated calibration updates, timing, and cancellation. Test discovery restores the fixtures and reports from `regression-data.zip` automatically. You can also restore them with `python prepare_fixtures.py`.

Tests mock input or replay saved images; they do not start a live game. The regression bundle contains only the canvas crops needed by the tests and compact reports, rather than the complete runtime history.

## Validation Status

This is an experimental assistant tested through multiple live Windows sessions. Screenshot detection, mouse dispatch, registered landings, and center-bonus hits are separate outcomes. Uncovered platform appearances and camera-registration failures remain possible. Uninterrupted play and reliable performance in every game above 3,000 points have not been established.

## Research and Development Notes

The detailed notes below are currently in Chinese:

- [Reference implementations and pinned revisions](研究记录.md)
- [Center-target precision](中心加分点精度优化.md)
- [Shadow filtering](阴影排除修复.md)
- [Long-running calibration stability](长时间运行稳定性修复.md)
- [Edge-landing recovery](边缘落地卡住修复.md)
- [Tile grouping and pixel calibration](魔方平台与自动像素校准.md)

Historical notes describe earlier interfaces as well as later fixes. Follow this README for the current launch procedure. Run `python prepare_fixtures.py` to restore the referenced `evidence/` reports.

## License

The original source code is licensed under the [MIT License](LICENSE). Third-party game imagery in regression screenshots remains the property of its respective rights holders and is not relicensed by this project. Reference projects and their investigated licenses are recorded in the research notes; their code and asset collections are not bundled.

This independent project is not affiliated with or endorsed by Tencent or WeChat.
